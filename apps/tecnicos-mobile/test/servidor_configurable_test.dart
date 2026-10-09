import 'package:campo/core/api/api_endpoints.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/auth/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/sesion_en_el_telefono.dart';

/// El servidor se elige desde el teléfono, y lo elegido manda.
///
/// POR QUÉ ESTO EXISTE
/// -------------------
/// El campo de servidor existía desde el principio, pero sólo en las
/// compilaciones de depuración, y —lo importante— **no hacía nada**. La URL se
/// guardaba en el almacenamiento seguro, el interceptor de Dio la ponía como
/// `baseUrl` de cada pedido, y ahí moría: `ApiEndpoints` arma rutas absolutas
/// (`'$baseUrl/api/auth/login/'`) sobre una variable que arrancaba con el
/// valor de compilación y no la tocaba nadie. Una ruta absoluta le gana al
/// `baseUrl` del pedido, así que el dominio que alguien escribía se guardaba
/// prolijamente y los pedidos seguían saliendo al de siempre.
///
/// Eso se veía como un error de conexión sin explicación: un APK compilado
/// sin `--dart-define=BACKEND_URL` apuntaba a `127.0.0.1` —dentro del teléfono
/// eso es el teléfono mismo— y no había forma de corregirlo desde el aparato.
/// La única salida era recompilar e instalar de nuevo en cada equipo.
///
/// Las dos primeras pruebas son la guarda de eso: no afirman que el campo
/// exista, afirman que cambiarlo cambia a dónde sale el pedido.
void main() {
  final SesionEnElTelefono sesion =
      SesionEnElTelefono(orgId: 'org-1', profileId: 'perfil-1');

  setUp(sesion.instalar);
  tearDown(() {
    sesion.desinstalar();
    // La variable es global al proceso: devolverla evita que una prueba le
    // deje el servidor cambiado a la siguiente.
    ApiEndpoints.baseUrl = ApiEndpoints.defaultEnvironmentUrl;
  });

  group('Servidor configurable desde la aplicación', () {
    test('1. Elegir un servidor cambia a dónde salen los pedidos', () async {
      final SecureStorageService almacen = SecureStorageService();

      await almacen.setBaseUrl('https://servidor-elegido.ejemplo.co');

      expect(await almacen.getBaseUrl(), 'https://servidor-elegido.ejemplo.co');
      expect(
        ApiEndpoints.login,
        'https://servidor-elegido.ejemplo.co/api/auth/login/',
        reason: 'guardarlo sin que las rutas lo usen es el defecto original',
      );
      expect(ApiEndpoints.trabajos,
          startsWith('https://servidor-elegido.ejemplo.co'));
    });

    test('2. Cerrar sesión NO borra el servidor elegido', () async {
      // Un teléfono de cuadrilla pasa de mano en mano: el servidor es del
      // aparato, no de la persona. Si se borrara al salir, cada técnico
      // tendría que volver a escribirlo, y escribirlo mal es justamente el
      // problema que esto viene a evitar.
      final SecureStorageService almacen = SecureStorageService();
      await almacen.setBaseUrl('https://servidor-elegido.ejemplo.co');

      await almacen.clearSession();

      expect(await almacen.getBaseUrl(), 'https://servidor-elegido.ejemplo.co');
    });

    testWidgets('3. El login dice a dónde apunta, sin abrir nada',
        (WidgetTester t) async {
      // Alguien está por escribir su contraseña. Saber a qué servidor la
      // manda es la contrapartida de poder cambiarlo: si se puede apuntar la
      // aplicación a cualquier lado, el destino no puede estar escondido.
      final SecureStorageService almacen = SecureStorageService();
      await almacen.setBaseUrl('https://servidor-elegido.ejemplo.co');
      await almacen.clearSession();

      await t.pumpWidget(const MaterialApp(home: LoginScreen()));
      await t.pump();

      expect(find.text('servidor-elegido.ejemplo.co'), findsOneWidget);
      // Plegado: quien entra todos los días no tiene que ver el campo.
      expect(find.widgetWithText(TextFormField, 'Servidor'), findsNothing);
    });

    testWidgets('4. Se despliega, se edita y se puede volver al de fábrica',
        (WidgetTester t) async {
      final SecureStorageService almacen = SecureStorageService();
      await almacen.setBaseUrl('https://escrito-mal.ejemplo.co');
      await almacen.clearSession();

      await t.pumpWidget(const MaterialApp(home: LoginScreen()));
      await t.pump();

      await t.tap(find.text('escrito-mal.ejemplo.co'));
      await t.pump();
      expect(find.widgetWithText(TextFormField, 'Servidor'), findsOneWidget);

      await t.tap(find.byIcon(Icons.restart_alt));
      await t.pump();

      expect(await almacen.getBaseUrl(), ApiEndpoints.defaultEnvironmentUrl,
          reason: 'la salida para quien ya no sabe cuál era el bueno');
      expect(find.text(Uri.parse(ApiEndpoints.defaultEnvironmentUrl).host),
          findsOneWidget);
    });

    testWidgets('5. La línea de arriba sigue al campo mientras se escribe',
        (WidgetTester t) async {
      // Dos lugares de la misma pantalla no pueden decir servidores
      // distintos. Se vio en el emulador: el campo ya decía el nuevo y el
      // encabezado seguía mostrando el anterior, en la única pantalla cuya
      // razón de existir es no dejar dudas sobre a dónde va la contraseña.
      final SecureStorageService almacen = SecureStorageService();
      await almacen.setBaseUrl('https://viejo.ejemplo.co');
      await almacen.clearSession();

      await t.pumpWidget(const MaterialApp(home: LoginScreen()));
      await t.pump();
      await t.tap(find.text('viejo.ejemplo.co'));
      await t.pump();

      await t.enterText(find.widgetWithText(TextFormField, 'Servidor'),
          'https://nuevo.ejemplo.co');
      await t.pump();

      expect(find.text('nuevo.ejemplo.co'), findsOneWidget);
      expect(find.text('viejo.ejemplo.co'), findsNothing,
          reason: 'el encabezado no puede quedar mostrando el anterior');
    });

    test('6. Una dirección a medias no pasa por válida', () {
      // Se tipea con el pulgar, a veces al sol. Una dirección rota no falla
      // al escribirla: falla un rato después, como un "error de conexión"
      // que no se parece en nada a su causa.
      expect(LoginScreen.normalizarServidor('https://ejemplo.com'),
          'https://ejemplo.com');
      expect(LoginScreen.normalizarServidor('  https://ejemplo.com/  '),
          'https://ejemplo.com',
          reason: 'la ruta y la barra final sobran: ApiEndpoints pone la suya');
      expect(LoginScreen.normalizarServidor('http://192.168.1.10:8000'),
          'http://192.168.1.10:8000',
          reason: 'un servidor en la red de la oficina es un caso real');

      expect(LoginScreen.normalizarServidor('ejemplo.com'), isNull,
          reason: 'sin esquema, Dio no sabe a dónde ir');
      expect(LoginScreen.normalizarServidor('ftp://ejemplo.com'), isNull);
      expect(LoginScreen.normalizarServidor('https://'), isNull);
      expect(LoginScreen.normalizarServidor(''), isNull);
      // El caso exacto que apareció en el emulador al pegar texto encima de
      // otro: quedó `agent-api.rahttps` y la aplicación lo guardó sin chistar.
      expect(
        LoginScreen.normalizarServidor(
            'https://agent-api.rahttps://demo.ejemplo.co'),
        isNull,
      );
    });

    testWidgets('7. Con una dirección rota lo dice, y no la guarda',
        (WidgetTester t) async {
      final SecureStorageService almacen = SecureStorageService();
      await almacen.setBaseUrl('https://bueno.ejemplo.co');
      await almacen.clearSession();

      await t.pumpWidget(const MaterialApp(home: LoginScreen()));
      await t.pump();
      await t.tap(find.text('bueno.ejemplo.co'));
      await t.pump();
      await t.enterText(
          find.widgetWithText(TextFormField, 'Servidor'), 'ejemplo');
      await t.enterText(find.widgetWithText(TextFormField, 'Correo electrónico'),
          'alguien@ejemplo.co');
      await t.enterText(
          find.widgetWithText(TextFormField, 'Contraseña'), 'una-clave');

      await t.tap(find.text('INGRESAR AL SISTEMA'));
      await t.pump();

      expect(find.textContaining('no es válida'), findsOneWidget);
      expect(await almacen.getBaseUrl(), 'https://bueno.ejemplo.co',
          reason: 'lo que no se puede usar no reemplaza a lo que funcionaba');
    });
  });
}
