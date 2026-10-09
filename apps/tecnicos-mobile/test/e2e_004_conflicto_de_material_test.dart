import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:flutter_test/flutter_test.dart';

import 'apoyo/jornada_de_prueba.dart';
import 'apoyo/sesion_en_el_telefono.dart';

/// E2E-004 · Cuando el servidor dice que no.
///
/// POR QUÉ ESTE ESCENARIO
/// ----------------------
/// Un consumo puede volver rechazado por dos razones que no se parecen en
/// nada, y la aplicación las trató como una sola durante mucho tiempo:
///
/// - **Descuadre**: el saldo no coincide con lo que registró bodega. Lo
///   resuelve el técnico explicando qué pasó, y la jornada cierra.
/// - **Conflicto de identidad**: ese equipo ya figura instalado en otra
///   orden. No lo resuelve el técnico: lo destraba alguien con acceso al
///   inventario. Insistir desde la vereda no sirve, y confundirlo con un
///   faltante hace que la persona dude del serial que tiene en la mano.
///
/// Además hay una consecuencia que sólo se ve mirando el saldo: un movimiento
/// que el servidor NO aceptó no puede seguir descontando material. Si lo
/// hiciera, el técnico tendría menos material del que realmente lleva encima,
/// y la diferencia aparecería recién en el conteo del mes siguiente.
void main() {
  final JornadaDePrueba j = JornadaDePrueba('e2e_004.db');

  setUpAll(j.prepararElEntorno);
  setUp(j.empezar);
  tearDown(j.terminar);
  tearDownAll(j.cerrarTodo);

  Future<void> abrirMateriales(WidgetTester t) => montarConBaseReal(
        t,
        j.enApp(const MaterialesScreen(
          tecnico: 'Carlos Gómez',
          mostrarDatosFuturos: false,
        )),
      );

  group('E2E-004 · Conflicto de material', () {
    testWidgets('1. Un conflicto de serial se ve, con su equipo y su serie',
        (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '1', serie: '48575443-A190C');
        await j.elServidorResponde(
          id: 'mov-1',
          resultado: 'conflicto',
          motivo: 'Ya figura instalada en la OT #4720.',
        );
      });

      await abrirMateriales(t);

      expect(find.text('Ese equipo ya figura instalado'), findsOneWidget);
      expect(find.textContaining('48575443-A190C'), findsWidgets,
          reason: 'la serie es lo que identifica el equipo en discusión');
      expect(find.textContaining('Ya figura instalada en la OT #4720'),
          findsOneWidget);
    });

    testWidgets('2. Y dice a quién acudir, no que lo explique',
        (WidgetTester t) async {
      // La diferencia que importa: este no se arregla explicando.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '1', serie: '48575443-A190C');
        await j.elServidorResponde(id: 'mov-1', resultado: 'conflicto');
      });

      await abrirMateriales(t);

      expect(find.textContaining('Revisalo con tu supervisor'), findsOneWidget);
      expect(
        find.textContaining('Explicá qué pasó'),
        findsNothing,
        reason: 'ese es el camino del descuadre, y acá no sirve',
      );
    });

    testWidgets('3. Un descuadre dice lo contrario', (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.elServidorResponde(
          id: 'mov-1',
          resultado: 'descuadre',
          motivo: 'El saldo no coincide con lo que registró bodega.',
        );
      });

      await abrirMateriales(t);

      expect(find.text('No cuadra con el kit'), findsOneWidget);
      expect(find.textContaining('Explicá qué pasó'), findsOneWidget);
      expect(find.textContaining('supervisor'), findsNothing);
    });

    testWidgets('4. Lo rechazado NO sigue descontando material',
        (WidgetTester t) async {
      // El punto que no se ve en el texto de la novedad y sí en el número: el
      // servidor no contabilizó ese consumo, así que el material sigue siendo
      // del técnico. Descontarlo igual le daría menos de lo que lleva encima.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.elServidorResponde(id: 'mov-1', resultado: 'conflicto');
      });

      await abrirMateriales(t);

      expect(
        find.textContaining('10 Disp.'),
        findsWidgets,
        reason: 'el servidor no aceptó el consumo: los dos conectores siguen '
            'siendo del técnico hasta que alguien resuelva el conflicto',
      );
    });

    testWidgets('5. Los dos tipos conviven sin mezclarse',
        (WidgetTester t) async {
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '2');
        await j.consumir(id: 'mov-2', cantidad: '1', serie: '48575443-A190C');
        await j.elServidorResponde(id: 'mov-1', resultado: 'descuadre');
        await j.elServidorResponde(id: 'mov-2', resultado: 'conflicto');
      });

      await abrirMateriales(t);

      expect(find.text('2 novedades'), findsOneWidget);
      expect(find.text('No cuadra con el kit'), findsOneWidget);
      expect(find.text('Ese equipo ya figura instalado'), findsOneWidget);
      // Cada uno con su camino, en la misma pantalla.
      expect(find.textContaining('Explicá qué pasó'), findsOneWidget);
      expect(find.textContaining('Revisalo con tu supervisor'), findsOneWidget);
    });

    testWidgets('6. Y la novedad llega hasta el inicio de la jornada',
        (WidgetTester t) async {
      // Un conflicto sin resolver no puede quedarse sólo en la pantalla de
      // materiales: el servidor lo declara al evaluar el cierre, y ahí es
      // donde el técnico se entera de que no va a poder cerrar.
      j.pantallaAlta(t);
      await t.runAsync(() async {
        await j.limpiar();
        await j.sembrarKit();
        await j.consumir(id: 'mov-1', cantidad: '1', serie: '48575443-A190C');
        await j.elServidorResponde(id: 'mov-1', resultado: 'conflicto');
        await j.sembrarJornada(
          motivos: <String>[
            'El equipo con serie 48575443-A190C ya figura instalado en otra orden.',
          ],
        );
      });

      await abrirMateriales(t);

      expect(find.text('Ese equipo ya figura instalado'), findsOneWidget);

      final bool puede = (await t.runAsync(() async {
        final estado = await j.db.getJornada(
          orgId: JornadaDePrueba.org,
          profileId: JornadaDePrueba.perfil,
        );
        return (estado?['puede_cerrar'] as int? ?? 0) == 1;
      }))!;
      expect(puede, isFalse, reason: 'con esto sin resolver no se cierra');
    });
  });
}
