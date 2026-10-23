import 'dart:async';
import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../api/api_client.dart';
import '../api/api_endpoints.dart';
import '../storage/local_database.dart';
import '../storage/secure_storage_service.dart';

/// El golpecito en el hombro: que el teléfono avise sin que nadie abra la app.
///
/// QUÉ RESUELVE, Y QUÉ NO
/// ----------------------
/// La notificación **ya existía** antes de esto: la escribe la plataforma
/// (`common/notifications.py`), la espeja la cola en `local_notificaciones` y la
/// dibuja [NotificacionesScreen]. Lo único que faltaba era que el técnico se
/// enterara **sin abrir la aplicación**. Eso es todo lo que agrega este archivo.
///
/// La consecuencia importante: **el push no es la fuente de verdad**. Si no
/// llega —teléfono sin señal, avisos apagados, batería en ahorro— el registro
/// está igual del otro lado y aparece en la próxima sincronización. Por eso acá
/// nada depende de que un mensaje llegue, y el mensaje que llega se guarda en la
/// misma tabla que el resto en vez de en una paralela.
///
/// POR QUÉ FCM Y NO EL BACKEND QUE YA TENEMOS
/// ------------------------------------------
/// En Android el único canal que despierta una app cerrada es el del sistema
/// operativo, y ese canal es FCM. Supabase Realtime, un WebSocket o un `poll`
/// necesitan proceso vivo, o sea la app en primer plano: justo el caso en que el
/// técnico ya está mirando la pantalla. No es una preferencia, es el único
/// camino.
///
/// LO QUE ESTE CÓDIGO NO PUEDE HACER
/// ---------------------------------
/// **No puede romper el arranque.** Firebase puede faltar —un APK compilado sin
/// `google-services.json`—, el permiso puede estar negado y la red puede no
/// estar. Las tres cosas dejan la app funcionando igual y sin push, porque la
/// alternativa sería que un técnico no pueda ver sus trabajos por un problema de
/// notificaciones. De ahí que [arrancar] no lance nunca.
class AvisosPush {
  AvisosPush({
    ApiClient? api,
    LocalDatabase? baseLocal,
    SecureStorageService? almacen,
    FirebaseMessaging? mensajeria,
    FlutterLocalNotificationsPlugin? locales,
  })  : _api = api ?? ApiClient(),
        _base = baseLocal ?? LocalDatabase(),
        _almacen = almacen ?? SecureStorageService(),
        _mensajeriaInyectada = mensajeria,
        _localesInyectadas = locales;

  final ApiClient _api;
  final LocalDatabase _base;
  final SecureStorageService _almacen;
  final FirebaseMessaging? _mensajeriaInyectada;
  final FlutterLocalNotificationsPlugin? _localesInyectadas;

  /// El id del canal de Android.
  ///
  /// Tiene que ser **el mismo** que `default_notification_channel_id` del
  /// AndroidManifest.xml. Si no coincide, Android no falla: mete los avisos que
  /// llegan con la app cerrada en un canal "Miscellaneous" sin sonido, y el
  /// técnico no se entera de nada. Es la clase de desajuste que nadie encuentra
  /// leyendo código.
  static const String canal = 'avisos_de_campo';

  /// Qué hacer cuando el técnico toca el aviso. Se completa desde el shell.
  static void Function(String ordenId)? alAbrirOrden;

  /// La orden que quedó pendiente de abrir porque el aviso se tocó antes de que
  /// hubiera una pantalla donde abrirla.
  ///
  /// Pasa de verdad: tocar la notificación con la app cerrada arranca el proceso
  /// desde cero, y `getInitialMessage` contesta antes de que el shell exista.
  /// Sin esta cola de una sola posición, ese toque abre la aplicación en la
  /// pantalla de inicio y el aviso se pierde.
  static String? _ordenPendiente;

  StreamSubscription<RemoteMessage>? _suscripcionMensajes;
  StreamSubscription<String>? _suscripcionToken;

  /// Enciende el push. No lanza: cualquier fallo deja la app sin push y andando.
  ///
  /// Devuelve si quedó registrado en el servidor, que es lo único verificable
  /// desde afuera: que haya token no significa que el servidor lo tenga.
  Future<bool> arrancar() async {
    try {
      await Firebase.initializeApp();
    } catch (e) {
      // Sin `google-services.json` en el APK esto falla. No es un caso
      // hipotético: es el estado del build hasta que alguien pone el archivo.
      debugPrint('push: Firebase no arrancó (${e.runtimeType})');
      return false;
    }

    // Se registra DESPUES de inicializar y antes de escuchar. Sin un manejador
    // registrado, Firebase imprime un aviso en cada mensaje que llega con la
    // app cerrada; y el día que un aviso salga sin bloque `notification` --uno
    // de datos puros-- no habría dónde engancharlo.
    try {
      FirebaseMessaging.onBackgroundMessage(manejadorDeSegundoPlano);
    } catch (e) {
      debugPrint('push: sin manejador de segundo plano (${e.runtimeType})');
    }

    final FirebaseMessaging mensajeria =
        _mensajeriaInyectada ?? FirebaseMessaging.instance;

    try {
      await _crearCanal();

      // Android 13+ lo pide explícitamente. Negado, el teléfono acepta el
      // registro y descarta cada aviso en silencio: sin error y sin log.
      final NotificationSettings permiso =
          await mensajeria.requestPermission(alert: true, badge: true, sound: true);
      if (permiso.authorizationStatus == AuthorizationStatus.denied) {
        debugPrint('push: el técnico negó el permiso');
        // Se sigue igual: el token sirve para cuando lo conceda más adelante
        // desde los ajustes del teléfono, y no hay por qué volver a preguntar.
      }

      _escuchar(mensajeria);

      final String? token = await mensajeria.getToken();
      if (token == null || token.isEmpty) return false;
      return await _registrar(token);
    } catch (e) {
      debugPrint('push: no se pudo encender (${e.runtimeType})');
      return false;
    }
  }

  /// El canal de Android, con su nombre y su importancia.
  ///
  /// Se crea al arrancar y no al recibir el primer aviso: un canal que no existe
  /// cuando llega el mensaje hace que Android lo ponga en uno por omisión, y la
  /// importancia de un canal **no se puede subir después**. Si nace en `low`,
  /// nunca suena, ni reinstalando la app.
  Future<void> _crearCanal() async {
    final FlutterLocalNotificationsPlugin locales =
        _localesInyectadas ?? FlutterLocalNotificationsPlugin();
    await locales.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      ),
      onDidReceiveNotificationResponse: _alTocarLaLocal,
    );
    final AndroidFlutterLocalNotificationsPlugin? android =
        locales.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
    await android?.createNotificationChannel(
      const AndroidNotificationChannel(
        canal,
        'Avisos de trabajo',
        description:
            'Trabajos devueltos para corregir y avisos del supervisor.',
        importance: Importance.high,
      ),
    );
  }

  void _escuchar(FirebaseMessaging mensajeria) {
    // Con la app abierta Android NO dibuja nada: el sistema asume que si la
    // persona está mirando, la app se encarga. Sin esta rama el aviso llegaba y
    // no pasaba nada visible.
    _suscripcionMensajes?.cancel();
    _suscripcionMensajes = FirebaseMessaging.onMessage.listen(_alLlegar);

    // El token cambia solo: al reinstalar, al limpiar datos, cada tanto por
    // decisión de Google. Un token viejo no da error — simplemente deja de
    // entregar, en silencio, hasta que alguien se pregunta por qué.
    _suscripcionToken?.cancel();
    _suscripcionToken = mensajeria.onTokenRefresh.listen(_registrar);

    // Tocar el aviso con la app en segundo plano.
    FirebaseMessaging.onMessageOpenedApp.listen(_alTocar);

    // Y tocarlo con la app cerrada, que arranca el proceso de cero.
    mensajeria.getInitialMessage().then((RemoteMessage? m) {
      if (m != null) _alTocar(m);
    });
  }

  /// Guarda el aviso que llegó con la app abierta y lo muestra.
  ///
  /// SE GUARDA ANTES DE MOSTRARSE, y es el mismo criterio que el resto del
  /// proyecto: *guardar primero, entregar después*. Un aviso que se dibuja y no
  /// se guarda desaparece al cerrar la app, y el técnico no tiene dónde volver a
  /// buscarlo.
  Future<void> _alLlegar(RemoteMessage mensaje) async {
    await espejar(mensaje);
    final RemoteNotification? n = mensaje.notification;
    if (n == null) return;
    try {
      final FlutterLocalNotificationsPlugin locales =
          _localesInyectadas ?? FlutterLocalNotificationsPlugin();
      await locales.show(
        id: mensaje.hashCode,
        title: n.title,
        body: n.body,
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            canal,
            'Avisos de trabajo',
            importance: Importance.high,
            priority: Priority.high,
          ),
        ),
        payload: (mensaje.data['enlace'] ?? '').toString(),
      );
    } catch (e) {
      debugPrint('push: no se pudo dibujar (${e.runtimeType})');
    }
  }

  /// Escribe el aviso en la misma tabla que la sincronización.
  ///
  /// POR QUÉ EN LA MISMA TABLA Y NO EN UNA PROPIA
  /// --------------------------------------------
  /// Porque es la misma notificación. El push y la sincronización son dos
  /// caminos hacia el mismo hecho, y `guardarNotificaciones` ya resuelve el
  /// choque: inserta si no está y **no pisa `leida_en`**, así que si el técnico
  /// la leyó por push y después baja la lista, no vuelve a aparecer sin leer.
  ///
  /// `id` viene del servidor en `data`. Sin él no se guarda: inventar uno acá
  /// crearía una fila que la sincronización duplicaría después.
  Future<void> espejar(RemoteMessage mensaje) async {
    final Map<String, dynamic> datos = mensaje.data;
    final String id = (datos['id'] ?? '').toString();
    if (id.isEmpty) return;

    final String? orgId = await _almacen.getOrgId();
    final String? profileId = await _almacen.getProfileId();
    if (orgId == null || profileId == null) return;

    try {
      await _base.guardarNotificaciones(
        orgId: orgId,
        profileId: profileId,
        // LAS CLAVES SON LAS DEL SERVIDOR, NO LAS DE LA COLUMNA
        // -----------------------------------------------------
        // `guardarNotificaciones` traduce de la forma que devuelve
        // `/api/notifications/` a la de la tabla, y lo hace para que haya UNA
        // sola traducción en la app. Pasarle las claves de la columna no da
        // error: inserta la fila con el verbo, el título, el enlace y la fecha
        // en blanco, y la lista muestra un aviso vacío que nadie puede abrir.
        notificaciones: <Map<String, dynamic>>[
          <String, dynamic>{
            'id': id,
            'verb': datos['verbo'] ?? '',
            'entity_name': mensaje.notification?.title ?? datos['titulo'] ?? '',
            'link': datos['enlace'] ?? '',
            'created_at': datos['creada_en'] ??
                DateTime.now().toUtc().toIso8601String(),
            'data': _comoMapa(datos['datos']),
            // Llega por push: nadie la leyó todavía. Se dice explícitamente en
            // vez de dejarlo a la ausencia de la clave, porque de eso depende
            // el contador de la barra.
            'read_at': null,
          },
        ],
      );
    } catch (e) {
      debugPrint('push: no se pudo espejar (${e.runtimeType})');
    }
  }

  /// El técnico tocó el aviso: abrir la orden, no la pantalla de inicio.
  void _alTocar(RemoteMessage mensaje) {
    abrirDesdeUnEnlace((mensaje.data['enlace'] ?? '').toString());
  }

  static void _alTocarLaLocal(NotificationResponse respuesta) {
    abrirDesdeUnEnlace(respuesta.payload ?? '');
  }

  /// `/ot/<id>` es el único formato que escribe el backend hoy.
  ///
  /// Un enlace de otra forma no se intenta adivinar: abre la app y nada más. El
  /// aviso sigue en la lista, que es donde el técnico lo va a encontrar.
  ///
  /// Pública a propósito: es la única parte de este archivo que se puede medir
  /// sin un teléfono y sin Firebase del otro lado, y es justo la que decide si
  /// el técnico termina en la orden o en la pantalla de inicio.
  static void abrirDesdeUnEnlace(String enlace) {
    if (!enlace.startsWith('/ot/')) return;
    final String ordenId = enlace.substring(4);
    if (ordenId.isEmpty) return;

    final void Function(String)? navegar = alAbrirOrden;
    if (navegar == null) {
      // Todavía no hay pantalla. Se guarda para que el shell lo consuma al
      // montarse.
      _ordenPendiente = ordenId;
      return;
    }
    navegar(ordenId);
  }

  /// La orden que un aviso dejó pendiente, una sola vez.
  ///
  /// Se consume al leerla a propósito: si quedara, cada vez que el shell se
  /// reconstruye volvería a abrir la misma orden.
  static String? tomarOrdenPendiente() {
    final String? pendiente = _ordenPendiente;
    _ordenPendiente = null;
    return pendiente;
  }

  /// Le dice al servidor cuál es este teléfono. Idempotente del otro lado.
  Future<bool> _registrar(String token) async {
    try {
      final r = await _api.post(
        ApiEndpoints.dispositivo,
        data: <String, dynamic>{'token': token, 'plataforma': 'android'},
      );
      return r.statusCode == 200 || r.statusCode == 201;
    } catch (e) {
      // Sin red el registro se reintenta en el próximo arranque. No se encola:
      // un token encolado puede estar vencido cuando la cola corra, y mandar un
      // token muerto es peor que no mandar nada —el servidor lo da de baja y el
      // teléfono queda sin avisos creyendo que está registrado—.
      debugPrint('push: no se pudo registrar (${e.runtimeType})');
      return false;
    }
  }

  /// Da de baja este teléfono para este perfil. Se llama al cerrar sesión.
  ///
  /// Un teléfono de cuadrilla pasa de mano en mano: el que entra no tiene por
  /// qué recibir los avisos del que salió.
  Future<void> darDeBaja() async {
    try {
      final FirebaseMessaging mensajeria =
          _mensajeriaInyectada ?? FirebaseMessaging.instance;
      final String? token = await mensajeria.getToken();
      if (token == null || token.isEmpty) return;
      await _api.delete(
        ApiEndpoints.dispositivo,
        data: <String, dynamic>{'token': token},
      );
    } catch (e) {
      debugPrint('push: no se pudo dar de baja (${e.runtimeType})');
    }
  }

  Future<void> apagar() async {
    await _suscripcionMensajes?.cancel();
    await _suscripcionToken?.cancel();
  }

  /// `data` de FCM es siempre `Map<String, String>`: lo que el backend manda
  /// como objeto llega serializado. Sin esto, `datos_json` guardaría la cadena
  /// `"{observacion: ...}"` —no JSON— y la pantalla no podría leerla.
  static Map<String, dynamic> _comoMapa(Object? crudo) {
    if (crudo is Map) return Map<String, dynamic>.from(crudo);
    if (crudo is String && crudo.isNotEmpty) {
      try {
        final Object? d = jsonDecode(crudo);
        if (d is Map) return Map<String, dynamic>.from(d);
      } catch (_) {
        // Un `data` que no es JSON no es un error del técnico: se descarta el
        // detalle y queda el aviso, que es lo que importa.
      }
    }
    return <String, dynamic>{};
  }
}

/// El manejador de segundo plano que Android exige.
///
/// POR QUÉ ESTÁ VACÍO Y NO ES UN OLVIDO
/// ------------------------------------
/// Los avisos salen con bloque `notification`, y a ésos Android los dibuja solo
/// cuando la app está en segundo plano: no hace falta código. Lo que no se puede
/// hacer acá es escribir en la base —este callback corre en un isolate aparte,
/// sin el estado de la app— y ese registro no se pierde: baja en la próxima
/// sincronización, que es la fuente de verdad.
///
/// Existe de todas formas porque sin un manejador registrado Firebase imprime un
/// aviso en cada mensaje y, el día que un aviso salga sin bloque `notification`,
/// no habría dónde engancharlo.
@pragma('vm:entry-point')
Future<void> manejadorDeSegundoPlano(RemoteMessage mensaje) async {}
