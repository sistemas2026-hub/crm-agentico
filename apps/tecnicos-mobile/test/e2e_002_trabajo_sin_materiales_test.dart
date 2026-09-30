import 'package:campo/features/ejecucion/ejecucion_screen.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';
import 'apoyo/sesion_en_el_telefono.dart';

/// E2E-002 · Un trabajo que no gasta material.
///
/// POR QUÉ ESTE ESCENARIO EXISTE
/// -----------------------------
/// La mayoría de los trabajos de campo no consumen nada: una revisión, una
/// reconfiguración, un diagnóstico que termina en "el problema está afuera".
/// Todo el módulo de materiales se construyó alrededor del caso que sí gasta,
/// y es fácil que el que no gasta quede pidiendo algo que no corresponde.
///
/// Lo que se mide es que el trabajo **se pueda cerrar sin tocar el kit**, y
/// que el checklist no invente un requisito de material que la plantilla no
/// pidió. Un requisito inventado deja a alguien sin poder terminar una orden
/// en la vereda, y la única salida es llamar a la oficina.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('e2e_002.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDownAll(j.cerrarTodo);

  group('E2E-002 · Trabajo sin materiales', () {
    testWidgets('1. Se abre y pide sólo lo que la plantilla pide',
        (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarOrden();
      });

      await montarConBaseReal(
        t,
        j.enApp(const EjecucionScreen(ordenId: JornadaDePrueba.ot)),
      );

      expect(find.text('OT #4832'), findsOneWidget);
      expect(find.textContaining('Tipo de intervención'), findsWidgets);
      // El bloque de materiales está, pero como invitación: nadie registró
      // nada y eso no es un problema.
      expect(find.textContaining('Todavía no registraste material'),
          findsOneWidget);
    });

    testWidgets('2. Sin material registrado, el checklist no lo exige',
        (WidgetTester t) async {
      // Este es el corazón del escenario. Un trabajo que no gasta material no
      // puede quedar trabado por no haber gastado material.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarOrden();
        // Todo lo que la plantilla SÍ pide, cumplido.
        await j.capturarEvidencia(requisitoId: 'foto_power_meter');
        await j.capturarEvidencia(requisitoId: 'foto_roseta');
        await j.capturarEvidencia(requisitoId: 'firma_cliente');
      });

      await montarConBaseReal(
        t,
        j.enApp(const EjecucionScreen(ordenId: JornadaDePrueba.ot)),
      );

      // Los campos obligatorios siguen faltando: eso sí lo pide la plantilla.
      expect(find.textContaining('Faltan 2 campos'), findsOneWidget);
      // Pero el material NO aparece como algo que bloquee.
      expect(
        find.textContaining('Falta registrar material'),
        findsNothing,
        reason: 'la plantilla no pidió material: exigirlo dejaría a alguien '
            'sin poder cerrar una orden que ya terminó',
      );
    });

    testWidgets('3. Con los campos respondidos, el cierre queda disponible',
        (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarOrden();
        await j.capturarEvidencia(requisitoId: 'foto_power_meter');
        await j.capturarEvidencia(requisitoId: 'foto_roseta');
        await j.capturarEvidencia(requisitoId: 'firma_cliente');
        await j.db.saveDatoCampo(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
          ordenId: JornadaDePrueba.ot,
          campoClave: 'potencia_rx',
          valor: '-18.4',
        );
        await j.db.saveDatoCampo(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
          ordenId: JornadaDePrueba.ot,
          campoClave: 'tipo_intervencion',
          valor: 'Roseta / Conector',
        );
      });

      await montarConBaseReal(
        t,
        j.enApp(const EjecucionScreen(ordenId: JornadaDePrueba.ot)),
      );

      expect(find.textContaining('Faltan'), findsNothing);
      expect(find.textContaining('Falta'), findsNothing,
          reason: 'no queda nada pendiente, y el kit nunca se tocó');
      expect(find.text('Finalizar orden'), findsOneWidget);

      // Hasta acá llega este escenario, a propósito.
      //
      // Tocar "Finalizar" con la fuente real dispara el servicio de cola, que
      // agenda un reintento con backoff. Ese timer sigue vivo después de que
      // el árbol se desmonta y el framework lo marca como error — con razón:
      // es un temporizador huérfano.
      //
      // Silenciarlo exigiría inyectarle una cola falsa a la pantalla, o sea
      // cambiar producción para poder probarla. No hace falta: que el botón
      // escribe la transición con su revisión ya está probado en
      // `ejecucion_pantalla_test.dart`, donde la fuente es un fixture y se
      // puede mirar qué se le pidió. Lo que este escenario agrega es lo otro:
      // que el botón esté HABILITADO en un trabajo que no gastó material.
    });

    testWidgets('4. Y el kit quedó intacto', (WidgetTester t) async {
      // Lo que no se tocó no se movió: un trabajo cerrado no puede descontar
      // material por su cuenta.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarOrden();
        await j.sembrarKit();
      });

      await montarConBaseReal(
        t,
        j.enApp(const EjecucionScreen(ordenId: JornadaDePrueba.ot)),
      );

      final List<Map<String, dynamic>> movimientos = (await t.runAsync(
        () => j.db.getMovimientosMaterialSinConfirmar(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
        ),
      ))!;
      expect(movimientos, isEmpty);
    });
  });
}
