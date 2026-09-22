import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// El kit que se ve en pantalla sale de la base, no de un catálogo de ejemplo.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Que el número que el técnico lee sea el que tiene en la camioneta **ahora**,
/// no el de la última vez que hubo señal. Esa diferencia es la que lo hace
/// llegar a la casa siguiente con material que ya gastó.
///
/// Y que el catálogo de ejemplo no tape nunca una jornada real: lo real le
/// gana al ejemplo, siempre.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_kit_jornada.db');

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';

  late LocalDatabase db;

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    for (final t in const ['local_kit', 'cola_movimientos_material']) {
      await base.delete(t);
    }
  });

  Future<void> darKit({String disponible = '24', String consumido = '0'}) async {
    await db.reemplazarKit(
      orgId: orgA,
      profileId: perfilA,
      materiales: <Map<String, dynamic>>[
        {
          'codigo': 'CON-SC-APC',
          'nombre': 'Conector SC/APC',
          'categoria': 'Conectividad',
          'clase': 'consumible',
          'unidad': 'unidades',
          'recibido': '24',
          'consumido': consumido,
          'devuelto': '0',
          'disponible': disponible,
          'series': <String>[],
          'acta': 'K-2024-094',
        },
      ],
    );
  }

  group('1. El saldo que se muestra incluye lo que no subió', () {
    test('Sin movimientos, es lo que dijo el servidor', () async {
      await darKit();

      final saldo = await db.saldoLocalDe(
        orgId: orgA, profileId: perfilA, codigo: 'CON-SC-APC',
      );

      expect(saldo, 24);
    });

    test('Un consumo sin subir ya descuenta', () async {
      await darKit();
      await db.encolarMovimientoMaterial(
        id: 'm1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', materialNombre: 'Conector SC/APC',
        tipo: 'consumo', cantidad: '4', ordenId: 'ot-1', ordenNumero: 4832,
      );

      final saldo = await db.saldoLocalDe(
        orgId: orgA, profileId: perfilA, codigo: 'CON-SC-APC',
      );

      expect(saldo, 20, reason: 'lo que ya puso, ya no lo tiene');
    });

    test('El kit leído refleja lo usado, subido o no', () async {
      await darKit(consumido: '2', disponible: '22');
      await db.encolarMovimientoMaterial(
        id: 'm1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', materialNombre: 'Conector SC/APC',
        tipo: 'consumo', cantidad: '3', ordenId: 'ot-1',
      );

      final kit = await KitDeJornada.leer(
        baseLocal: db,
        almacenamiento: _SesionFalsa(orgA, perfilA),
      );

      final material = kit.materiales.single;
      expect(material.recibidos, 24);
      expect(material.usados, 5, reason: '2 confirmados + 3 esperando');
      expect(material.disponibles, 19);
    });
  });

  group('2. Lo que hay que mirar no se esconde', () {
    test('Un descuadre confirmado sigue apareciendo', () async {
      await darKit();
      await db.encolarMovimientoMaterial(
        id: 'm1', orgId: orgA, profileId: perfilA,
        materialCodigo: 'CON-SC-APC', materialNombre: 'Conector SC/APC',
        tipo: 'consumo', cantidad: '90', ordenId: 'ot-1',
      );
      await db.confirmarMovimientoMaterial(
        id: 'm1', orgId: orgA, profileId: perfilA,
        resultado: 'descuadre', motivo: 'Se registraron 90 y había 24.',
      );

      final kit = await KitDeJornada.leer(
        baseLocal: db,
        almacenamiento: _SesionFalsa(orgA, perfilA),
      );

      expect(kit.conNovedad, hasLength(1));
      expect(kit.conNovedad.first.titulo, 'No cuadra con el kit');
      expect(kit.conNovedad.first.motivo, contains('90'));
    });

    test('Y cuenta cuántos movimientos esperan turno', () async {
      await darKit();
      for (final id in <String>['m1', 'm2']) {
        await db.encolarMovimientoMaterial(
          id: id, orgId: orgA, profileId: perfilA,
          materialCodigo: 'CON-SC-APC', tipo: 'consumo', cantidad: '1',
          ordenId: 'ot-1',
        );
      }

      final kit = await KitDeJornada.leer(
        baseLocal: db,
        almacenamiento: _SesionFalsa(orgA, perfilA),
      );

      expect(kit.sinSubir, 2);
    });
  });

  group('3. Sin identidad no se lee nada', () {
    test('Sin sesión, el kit viene vacío en vez de fallar', () async {
      await darKit();

      final kit = await KitDeJornada.leer(
        baseLocal: db,
        almacenamiento: _SesionFalsa(null, null),
      );

      expect(kit.hayAlgo, isFalse);
      expect(kit.materiales, isEmpty);
    });

    test('El kit de otra persona no se ve', () async {
      await darKit();

      final kit = await KitDeJornada.leer(
        baseLocal: db,
        almacenamiento: _SesionFalsa(orgA, 'prof_pedro'),
      );

      expect(kit.hayAlgo, isFalse);
    });
  });

  group('4. Lo real le gana al ejemplo', () {
    testWidgets('Con kit real, el catálogo de demostración no aparece',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1000, 4200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      const real = KitDeJornada(
        materiales: <MaterialEnCustodia>[
          MaterialEnCustodia(
            categoria: 'Conectividad',
            nombre: 'Conector de la jornada real',
            detalle: 'CON-REAL',
            clase: ClaseMaterial.consumible,
            recibidos: 10,
            usados: 3,
            unidad: 'unidades',
          ),
        ],
        acta: 'K-REAL',
        sinSubir: 0,
        conNovedad: <MovimientoConNovedad>[],
      );

      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.lightTheme,
        home: const Scaffold(
          // El modo demostración está ENCENDIDO y aun así manda lo real.
          body: MaterialesScreen(mostrarDatosFuturos: true, kit: real),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Conector de la jornada real'), findsOneWidget);
    });

    testWidgets('Sin kit y sin demostración, lo dice sin inventar cifras',
        (WidgetTester tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: MaterialesScreen(
            mostrarDatosFuturos: false,
            kit: KitDeJornada.vacio(),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('no hay material entregado a tu nombre'),
        findsOneWidget,
      );
    });
  });
}

/// Una sesión de mentira, para no depender del canal del almacenamiento seguro.
class _SesionFalsa implements SecureStorageLectura {
  _SesionFalsa(this._org, this._perfil);

  final String? _org;
  final String? _perfil;

  @override
  Future<String?> getOrgId() async => _org;

  @override
  Future<String?> getProfileId() async => _perfil;
}
