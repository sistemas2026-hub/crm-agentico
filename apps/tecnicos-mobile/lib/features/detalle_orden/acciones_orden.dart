import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';

import '../../core/storage/local_database.dart';
import '../../core/storage/secure_storage_service.dart';
import '../../core/sync/sync_queue_service.dart';

/// Ejecutar una transición de estado, igual que antes.
///
/// El mecanismo no cambió en esta fase: se guarda el estado nuevo en la base
/// local y se encola la mutación en la misma transacción —así, sin señal, la
/// orden avanza igual y el servidor se entera cuando puede— y recién después
/// se intenta enviar. Lo único nuevo es que está detrás de una interfaz, para
/// poder probar la pantalla sin base ni red.
class AccionesOrden {
  const AccionesOrden({
    required this.transicionar,
    required this.sincronizar,
    this.probarConexion,
    this.medirSenal,
  });

  /// [tipoAccion] es el nombre que la cola le manda al backend
  /// (`marcar_en_camino`, `iniciar`, `completar`).
  final Future<void> Function({
    required String ordenId,
    required String nuevoEstadoLocal,
    required String tipoAccion,
    required int revisionBase,
  }) transicionar;

  final Future<void> Function() sincronizar;

  /// Probar la conexion del cliente, AHORA, parado en la casa.
  ///
  /// No pasa por la cola y no es un descuido: la cola existe para lo que
  /// cambia el mundo y puede esperar. Un ping encolado se ejecutaria cuando el
  /// tecnico ya se fue, midiendo un momento que a nadie le importa y con cara
  /// de respuesta a lo que pregunto. Sin señal se dice que no se pudo, y ya.
  final Future<ResultadoPing> Function(String ordenId, int paquetes)?
      probarConexion;

  /// Volver a medir la señal optica, AHORA.
  ///
  /// Mismo criterio que el ping, y por el mismo motivo: no pasa por la cola.
  /// Una medicion que se ejecuta cuando el tecnico ya se fue mide un momento
  /// que a nadie le importa, y llega con cara de respuesta a lo que pregunto.
  final Future<MedicionDeSenal> Function(String ordenId)? medirSenal;

  factory AccionesOrden.reales() {
    final baseLocal = LocalDatabase();
    final almacenamiento = SecureStorageService();
    final sincronizacion = SyncQueueService();

    return AccionesOrden(
      transicionar: ({
        required String ordenId,
        required String nuevoEstadoLocal,
        required String tipoAccion,
        required int revisionBase,
      }) async {
        final orgId = await almacenamiento.getOrgId();
        final profileId = await almacenamiento.getProfileId();
        if (orgId == null || profileId == null) return;

        await baseLocal.transicionarEstadoLocal(
          orgId: orgId,
          profileId: profileId,
          ordenId: ordenId,
          nuevoEstadoLocal: nuevoEstadoLocal,
          tipoAccion: tipoAccion,
          revisionBase: revisionBase,
          idempotencyKey: const Uuid().v4(),
        );

        // Oportunista: si hay señal sale ahora; si no, queda en la cola.
        await sincronizacion.procesarCola();
      },
      sincronizar: sincronizacion.procesarCola,
      medirSenal: (String ordenId) async {
        try {
          final Response<dynamic> r = await ApiClient().dio.post<dynamic>(
                ApiEndpoints.trabajoMedirSenal(ordenId),
              );
          return MedicionDeSenal.desde(r.data as Map<String, dynamic>?);
        } on DioException catch (e) {
          if (e.response?.statusCode == 409) {
            // La orden no tiene serial. No es un problema de red y no se
            // reintenta: no hay a que equipo preguntarle.
            return const MedicionDeSenal.noSePudo('sin_equipo');
          }
          final bool sinRed = e.type == DioExceptionType.connectionError ||
              e.type == DioExceptionType.connectionTimeout ||
              e.type == DioExceptionType.receiveTimeout;
          return MedicionDeSenal.noSePudo(sinRed ? 'sin_conexion' : 'servidor');
        }
      },
      probarConexion: (String ordenId, int paquetes) async {
        try {
          final Response<dynamic> r = await ApiClient().dio.post<dynamic>(
                ApiEndpoints.trabajoProbarConexion(ordenId),
                data: <String, dynamic>{'paquetes': paquetes},
              );
          return ResultadoPing.desde(r.data as Map<String, dynamic>?);
        } on DioException catch (e) {
          // Sin conexion es el caso NORMAL de esta aplicacion, no una
          // excepcion: se nombra distinto que un rechazo del servidor porque
          // el tecnico tiene que saber si volver a intentar mas tarde o si el
          // problema es otro.
          final bool sinRed = e.type == DioExceptionType.connectionError ||
              e.type == DioExceptionType.connectionTimeout ||
              e.type == DioExceptionType.receiveTimeout;
          return ResultadoPing.noSePudo(sinRed ? 'sin_conexion' : 'servidor');
        }
      },
    );
  }
}

/// Lo que devuelve un ping, con la distincion que importa: **no se pudo
/// medir** no es lo mismo que **se midio y no respondio**. La primera se
/// reintenta; la segunda es un dato sobre el equipo del cliente.
class ResultadoPing {
  const ResultadoPing({
    required this.medido,
    this.respondieron = '',
    this.paquetes = const <PaqueteDePing>[],
    this.motivo = '',
  });

  factory ResultadoPing.desde(Map<String, dynamic>? cuerpo) {
    final Map<String, dynamic> d = cuerpo ?? <String, dynamic>{};
    if (d['medido'] != true) {
      return ResultadoPing.noSePudo(d['motivo']?.toString() ?? 'desconocido');
    }
    return ResultadoPing(
      medido: true,
      respondieron: d['respondieron']?.toString() ?? '',
      paquetes: (d['paquetes'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<dynamic, dynamic>>()
          .map(PaqueteDePing.desde)
          .toList(),
    );
  }

  factory ResultadoPing.noSePudo(String motivo) =>
      ResultadoPing(medido: false, motivo: motivo);

  final bool medido;

  /// Texto crudo de WispHub: '10 de 10', '0 de 10'. **No se convierte a
  /// numero**: esta medido dos veces que el mismo equipo sano da 1, 2 y 3 de 3
  /// en corridas seguidas, asi que no es una escala -- es una muestra.
  final String respondieron;

  /// Los diez, uno por uno. Un promedio esconde si el enlace es intermitente o
  /// esta caido parejo, que es justo lo que decide que hace el tecnico -- y
  /// con tres muestras esa diferencia no se dibuja.
  final List<PaqueteDePing> paquetes;

  final String motivo;
}

/// Un intento del ping: cual fue, si volvio, y cuanto tardo.
///
/// 'respondio' llega resuelto del backend y no se deduce del texto del tiempo:
/// un paquete perdido trae el tiempo vacio, y leer "sin tiempo" como "no
/// volvio" funcionaria hasta el dia que el proveedor mande un cero.
class PaqueteDePing {
  const PaqueteDePing({
    required this.n,
    required this.respondio,
    this.rtt = '',
    this.perdida = '',
    this.host = '',
  });

  factory PaqueteDePing.desde(Map<dynamic, dynamic> d) => PaqueteDePing(
        n: int.tryParse('${d['n']}') ?? 0,
        respondio: d['respondio'] == true,
        rtt: d['rtt']?.toString() ?? '',
        perdida: d['perdida']?.toString() ?? '',
        host: d['host']?.toString() ?? '',
      );

  final int n;
  final bool respondio;
  final String rtt;
  final String perdida;

  /// Quién contestó. Es la IP del cliente, la misma en los diez -- y si
  /// alguna vez no lo fuera, eso sería justo lo que hay que ver.
  final String host;
}

/// Una medición de señal pedida desde el terreno, con la distinción que
/// importa: **no se pudo medir** no es lo mismo que **se midió y está mal**.
///
/// La primera se reintenta; la segunda es un dato sobre el equipo del cliente, y
/// manda al técnico a revisar la planta. Confundirlas le hace buscar una falla
/// que no existe, que es exactamente lo que esta pantalla vino a evitar.
///
/// NO REEMPLAZA A LA LECTURA DE LA FICHA. La de la ficha es el registro de cómo
/// estaba el servicio **antes** de la visita; ésta es cómo está **ahora**. Las
/// dos juntas son lo que permite decir si la visita sirvió — y por eso viajan
/// separadas y cada una con su hora.
class MedicionDeSenal {
  const MedicionDeSenal({
    required this.medido,
    this.motivo = '',
    this.medidoEn,
    this.senal1490,
    this.senal1310,
    this.veredicto = '',
    this.estadoOnu = '',
  });

  const MedicionDeSenal.noSePudo(String motivo)
      : this(medido: false, motivo: motivo);

  /// Si se pudo preguntar y hubo respuesta.
  final bool medido;

  /// Por qué no se pudo. Vacío cuando sí se midió.
  final String motivo;

  final DateTime? medidoEn;
  final double? senal1490;
  final double? senal1310;
  final String veredicto;
  final String estadoOnu;

  factory MedicionDeSenal.desde(Map<String, dynamic>? cuerpo) {
    if (cuerpo == null) return const MedicionDeSenal.noSePudo('respuesta_vacia');
    if (cuerpo['ok'] != true) {
      return MedicionDeSenal.noSePudo(
        (cuerpo['motivo'] ?? 'desconocido').toString(),
      );
    }
    final Object? crudo = cuerpo['lectura'];
    final Map<String, dynamic> lectura =
        crudo is Map ? Map<String, dynamic>.from(crudo) : <String, dynamic>{};
    return MedicionDeSenal(
      medido: true,
      medidoEn: DateTime.tryParse((cuerpo['medido_en'] ?? '').toString())
          ?.toLocal(),
      senal1490: _decimal(lectura['onu_signal_1490']),
      senal1310: _decimal(lectura['onu_signal_1310']),
      veredicto: (lectura['onu_signal_1490_veredicto'] ?? '').toString(),
      estadoOnu: (lectura['onu_status'] ?? '').toString(),
    );
  }

  /// SmartOLT manda la potencia como texto a veces (`'-21.19 dBm'`) y como
  /// número otras. Medido sobre la orden 1849 de producción: llegó como texto.
  /// Asumir una de las dos formas deja la tarjeta vacía la mitad de las veces.
  static double? _decimal(Object? v) {
    if (v is num) return v.toDouble();
    if (v is! String || v.trim().isEmpty) return null;
    return double.tryParse(
      v.replaceAll(RegExp(r'[^0-9eE+\-.]'), ''),
    );
  }

  /// Qué decirle al técnico cuando no se pudo.
  ///
  /// Cada motivo se arregla distinto: uno se reintenta más tarde, otro es
  /// configuración de la empresa y otro no se arregla nunca. Un mensaje único
  /// los mandaría a los tres al mismo lugar equivocado.
  String get explicacion => switch (motivo) {
        'sin_conexion' =>
          'Sin señal no se puede medir. No queda pendiente: volvé a intentar '
              'cuando tengas datos.',
        'sin_equipo' =>
          'Esta orden no tiene el serial del equipo cargado, así que no hay a '
              'qué equipo preguntarle.',
        'medicion_no_habilitada' =>
          'La empresa todavía no habilitó la medición en vivo. No es el equipo '
              'del cliente.',
        'motor_no_responde' || 'motor_rechazo' =>
          'El sistema no contestó. No dice nada del equipo del cliente: volvé '
              'a intentar.',
        'sin_lectura' || 'respuesta_vacia' =>
          'Contestó, pero sin niveles. No se sabe cómo está la señal.',
        _ => 'No se pudo medir.',
      };
}
