import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Una sesión iniciada, como la ve la aplicación.
///
/// POR QUÉ A NIVEL DE CANAL Y NO INYECTANDO
/// ----------------------------------------
/// Todas las pruebas anteriores le pasan a cada pantalla un
/// `SecureStorageLectura` de mentira. Eso alcanza para probar el dibujo, pero
/// deja sin probar el camino de verdad: en el teléfono nadie le inyecta nada a
/// `KitDeJornada.leer()`, que construye su propio `SecureStorageService` y
/// pregunta por el canal de plataforma.
///
/// Acá se responde ese canal. Las pantallas se montan **sin parámetros**, como
/// las construye la aplicación, y leen su identidad por el mismo camino. Si
/// alguien cambiara el nombre de una clave o el orden de una lectura, esto se
/// entera; las otras pruebas no.
///
/// El almacenamiento es un mapa en memoria: se puede escribir y volver a leer,
/// que es lo que hace el cierre de sesión.
class SesionEnElTelefono {
  SesionEnElTelefono({required this.orgId, required this.profileId});

  final String orgId;
  final String profileId;

  static const MethodChannel _canal =
      MethodChannel('plugins.it_nomads.com/flutter_secure_storage');

  final Map<String, String> _valores = <String, String>{};

  /// Enchufa la sesión. Devuelve la función que la desenchufa.
  void instalar() {
    _valores
      ..clear()
      ..addAll(<String, String>{
        'dexter_current_org_id': orgId,
        'dexter_profile_id': profileId,
        'dexter_current_org_name': 'Rapilink ISP',
        'dexter_user_name': 'Carlos Gómez',
        'dexter_user_email': 'carlos@rapilink.co',
        'dexter_access_token': 'token-de-prueba',
      });

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_canal, (MethodCall llamada) async {
      final Map<Object?, Object?> args =
          (llamada.arguments as Map<Object?, Object?>?) ?? <Object?, Object?>{};
      final String clave = (args['key'] ?? '').toString();

      switch (llamada.method) {
        case 'read':
          return _valores[clave];
        case 'readAll':
          return Map<String, String>.from(_valores);
        case 'write':
          _valores[clave] = (args['value'] ?? '').toString();
          return null;
        case 'delete':
          _valores.remove(clave);
          return null;
        case 'deleteAll':
          _valores.clear();
          return null;
        case 'containsKey':
          return _valores.containsKey(clave);
        default:
          // Un método que no conocemos devuelve null en vez de explotar: el
          // plugin agrega alguno de vez en cuando y no queremos que eso tumbe
          // una prueba que no tiene nada que ver.
          return null;
      }
    });
  }

  void desinstalar() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_canal, null);
  }
}

/// Monta un widget y deja que su carga real termine.
///
/// POR QUÉ NO ALCANZA CON `pumpAndSettle`
/// --------------------------------------
/// `pumpAndSettle` avanza un reloj **falso**. Una pantalla que en `initState`
/// consulta SQLite queda esperando un futuro que nunca resuelve, porque el
/// tiempo de verdad no avanza: la prueba se cuelga sin decir por qué. Pasó una
/// vez en este proyecto y quedó como "no mezclar base con pruebas de widget",
/// cuando el problema era otro.
///
/// `runAsync` corre el código asíncrono fuera de ese reloj. Primero se deja
/// que la E/S real termine, y recién después se redibuja con el reloj de la
/// prueba para que las animaciones lleguen a reposo.
Future<void> montarConBaseReal(WidgetTester tester, Widget app) async {
  await tester.runAsync(() async {
    await tester.pumpWidget(app);
    await _dejarQueTermine(tester);
  });
}

/// Lo mismo, para cuando la pantalla ya está montada y hay que esperar a que
/// termine una lectura disparada por un toque.
Future<void> esperarLaBase(WidgetTester tester) async {
  await tester.runAsync(() => _dejarQueTermine(tester));
}

/// Después de un toque que abre una hoja o un diálogo.
///
/// Abrir un modal es una animación, y las animaciones sí avanzan con el reloj
/// de la prueba: para eso alcanza `pump` con una duración. Lo que no se puede
/// es pedirle a ese mismo reloj que espere a la base — por eso esto va
/// separado de `esperarLaBase`, y no combinado en un helper que haga las dos
/// cosas y se cuelgue la mitad de las veces.
Future<void> esperarLaAnimacion(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 350));
}

/// Deja correr la E/S real y redibuja, varias veces.
///
/// SIN `pumpAndSettle`, A PROPÓSITO
/// --------------------------------
/// `pumpAndSettle` espera a que no queden cuadros pendientes usando el reloj
/// **falso** de la prueba. Una pantalla que está esperando a SQLite no tiene
/// cuadros pendientes: tiene un futuro sin resolver, y ese futuro necesita
/// tiempo real. Llamarlo ahí es esperar para siempre — la prueba no falla,
/// se cuelga, que es peor porque no dice por qué.
///
/// Acá se alterna: un rato de tiempo real para que la base conteste, un
/// `pump` para que el árbol se entere. Tres vueltas alcanzan para las
/// cadenas que hay en estas pantallas —identidad, datos, y el redibujo que
/// dispara la suscripción a los cambios— y sobra para las de una sola.
Future<void> _dejarQueTermine(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await Future<void>.delayed(const Duration(milliseconds: 40));
    await tester.pump();
  }
}
