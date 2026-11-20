import 'package:campo/features/detalle_orden/seguimiento_de_la_intervencion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Quién puede destrabar un trabajo detenido, y por qué la frontera es ésa.
///
/// LA DECISIÓN QUE ESTE ARCHIVO DEFIENDE
/// -------------------------------------
/// El backend deja que el técnico asignado resuelva. La pregunta que importa no
/// es si **puede**, es si **sabe qué se hizo**: `que_se_hizo` es obligatorio del
/// otro lado, y existe para responder «¿por qué este trabajo tardó tres días?».
///
/// Si el bloqueo requiere al NOC y coordinación gestionó un permiso municipal,
/// el técnico no sabe qué gestionaron: escribiría «ya puedo entrar», y ese campo
/// quedaría inservible justo para la pregunta que lo justifica. Si NO requiere
/// NOC —esperando al cliente, falta un material que fue a buscar— el que sabe es
/// él.
///
/// Así que la frontera la marca `requiere_noc`, que ya existe, en vez de un
/// permiso nuevo. Las dos direcciones se afirman acá: con NOC **no** aparece la
/// salida, y sin NOC **sí**. Una sola de las dos se cumpliría por accidente
/// escondiendo el botón siempre.
///
/// LO OTRO QUE SE DEFIENDE
/// -----------------------
/// * **`bloqueada` y `requiere_noc` son dos conceptos.** Un bloqueo que no
///   detuvo el trabajo se anota y se sigue trabajando, y la pantalla lo dice.
/// * **Un `que_se_hizo` vacío no viaja.** Es cortesía —la validación de verdad
///   es del servidor— pero evita que el técnico crea que destrabó.
///
/// LO QUE ESTE ARCHIVO **NO** CUBRE, Y HAY QUE DECIRLO
/// --------------------------------------------------
/// La subida (`_subirResolucion`) y su tratamiento de códigos —409 «alguien lo
/// resolvió primero» se marca como hecho, 422 y 404 no se reintentan— no tiene
/// prueba automática: `SyncQueueService` construye su `ApiClient` como campo
/// fijo y no se puede falsear sin refactorizarlo. Se verifica contra el backend
/// de laboratorio, no acá. Decirlo es parte de la entrega: una prueba que no
/// existe no se cuenta como verde.
void main() {
  Future<void> montar(
    WidgetTester tester, {
    required Map<String, dynamic> bloqueo,
    void Function(String queSeHizo)? alResolver,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: SeguimientoDeLaIntervencion(
              seguimiento: <String, dynamic>{
                'eventos': <dynamic>[],
                'momentos_registrados': <String>[],
                'formularios': <String, dynamic>{},
                'bloqueo_abierto': bloqueo,
              },
              cargando: false,
              alResolverBloqueo: alResolver,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Map<String, dynamic> unBloqueo({
    bool requiereNoc = false,
    bool detuvo = true,
    int? minutos = 95,
    String motivo = 'La casa está cerrada y el cliente no contesta',
    String necesita = 'que el cliente confirme otra hora',
  }) {
    return <String, dynamic>{
      'requiere_noc': requiereNoc,
      'detuvo_el_trabajo': detuvo,
      'minutos_detenido': minutos,
      'motivo': motivo,
      'necesita': necesita,
    };
  }

  // Los widgets del diseño no son uniformes, y es a propósito:
  //   DexterAccionRapida      dibuja el texto tal cual   (el chip de abrir)
  //   DexterAccionDominante   dibuja `toUpperCase()`     (el botón grande)
  //   DexterPastilla          dibuja `toUpperCase()`
  const String abrir = 'Ya se puede seguir';
  const String destrabar = 'DESTRABAR EL TRABAJO';

  /// Abre la salida y escribe lo que se hizo. Devuelve lo que recibió la
  /// pantalla de arriba, o `null` si nunca la llamó.
  Future<String?> resolverCon(
    WidgetTester tester,
    String texto, {
    Map<String, dynamic>? bloqueo,
  }) async {
    String? recibido;
    await montar(
      tester,
      bloqueo: bloqueo ?? unBloqueo(),
      alResolver: (String q) => recibido = q,
    );

    await tester.ensureVisible(find.text(abrir));
    await tester.tap(find.text(abrir));
    await tester.pumpAndSettle();

    if (texto.isNotEmpty) {
      await tester.enterText(find.byType(TextField), texto);
      await tester.pumpAndSettle();
    }

    await tester.ensureVisible(find.text(destrabar));
    await tester.tap(find.text(destrabar));
    await tester.pumpAndSettle();

    return recibido;
  }

  group('1. La frontera es requiere_noc, en las dos direcciones', () {
    testWidgets('un bloqueo que NO requiere NOC ofrece la salida', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        bloqueo: unBloqueo(requiereNoc: false),
        alResolver: (String _) {},
      );

      expect(find.text(abrir), findsOneWidget);
    });

    testWidgets('un bloqueo que SÍ requiere NOC no la ofrece', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        bloqueo: unBloqueo(requiereNoc: true),
        alResolver: (String _) {},
      );

      expect(find.text(abrir), findsNothing);
      expect(find.byType(TextField), findsNothing);
    });

    testWidgets('y además dice quién lo va a destrabar', (
      WidgetTester tester,
    ) async {
      await montar(
        tester,
        bloqueo: unBloqueo(requiereNoc: true),
        alResolver: (String _) {},
      );

      // No alcanza con esconder el botón: alguien parado en la calle tiene que
      // saber qué está esperando, o va a llamar para preguntarlo.
      expect(
        find.textContaining('NOC o coordinación'),
        findsOneWidget,
      );
    });

    testWidgets('sin a quién entregarlo, tampoco hay salida', (
      WidgetTester tester,
    ) async {
      // La pantalla de arriba decide si corresponde ofrecerla. Un botón que no
      // lleva a ninguna parte le haría creer al técnico que destrabó.
      await montar(tester, bloqueo: unBloqueo(), alResolver: null);

      expect(find.text(abrir), findsNothing);
    });
  });

  group('2. Qué se hizo es obligatorio', () {
    testWidgets('vacío no viaja, y lo dice', (WidgetTester tester) async {
      final String? recibido = await resolverCon(tester, '');

      expect(recibido, isNull);
      expect(find.textContaining('Decí qué se hizo'), findsOneWidget);
    });

    testWidgets('con texto, llega tal cual a quien lo sube', (
      WidgetTester tester,
    ) async {
      final String? recibido = await resolverCon(
        tester,
        'El cliente volvió y abrió la casa',
      );

      expect(recibido, 'El cliente volvió y abrió la casa');
    });

    testWidgets('los espacios de los bordes no cuentan como texto', (
      WidgetTester tester,
    ) async {
      final String? recibido = await resolverCon(tester, '   ');

      expect(recibido, isNull);
      expect(find.textContaining('Decí qué se hizo'), findsOneWidget);
    });
  });

  group('3. Detenido y bloqueado no son lo mismo', () {
    testWidgets('si detuvo el trabajo, se ve cuánto lleva', (
      WidgetTester tester,
    ) async {
      await montar(tester, bloqueo: unBloqueo(detuvo: true, minutos: 95));

      expect(find.textContaining('95 min'), findsOneWidget);
      expect(find.text('TRABAJO DETENIDO'), findsOneWidget);
    });

    testWidgets('si NO detuvo el trabajo, dice que se puede seguir', (
      WidgetTester tester,
    ) async {
      await montar(tester, bloqueo: unBloqueo(detuvo: false, minutos: null));

      expect(find.text('BLOQUEO REPORTADO'), findsOneWidget);
      expect(
        find.textContaining('El estado del trabajo no cambió'),
        findsOneWidget,
      );
    });

    testWidgets('sin minutos no se inventa un número', (
      WidgetTester tester,
    ) async {
      await montar(tester, bloqueo: unBloqueo(detuvo: true, minutos: null));

      expect(find.textContaining('Detenido hace'), findsNothing);
    });
  });

  group('4. El motivo se lee, no se resume', () {
    testWidgets('el motivo y lo que hace falta se muestran', (
      WidgetTester tester,
    ) async {
      await montar(tester, bloqueo: unBloqueo());

      expect(
        find.text('La casa está cerrada y el cliente no contesta'),
        findsOneWidget,
      );
      expect(
        find.textContaining('que el cliente confirme otra hora'),
        findsOneWidget,
      );
    });

    testWidgets('sin bloqueo abierto, nada de esto ocupa lugar', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: SeguimientoDeLaIntervencion(
                seguimiento: <String, dynamic>{
                  'eventos': <dynamic>[],
                  'momentos_registrados': <String>[],
                  'formularios': <String, dynamic>{},
                  'bloqueo_abierto': null,
                },
                cargando: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('TRABAJO DETENIDO'), findsNothing);
      expect(find.text('BLOQUEO REPORTADO'), findsNothing);
      expect(find.text(abrir), findsNothing);
    });
  });
}
