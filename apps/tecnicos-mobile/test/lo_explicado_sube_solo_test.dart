import 'package:campo/core/storage/ciclo_de_vida_local.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/envio_automatico.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// UNA DIFERENCIA EXPLICADA SUBE SOLA, CON SEÑAL.
///
/// EL DEFECTO, REPORTADO EL 06/11/2026 POR QUIEN LO SUFRE
/// ------------------------------------------------------
/// «¿No se supone que teniendo la app conexión a internet debería mandar los
/// cambios sin tener que presionar nada?»
///
/// Sí. `EnvioAutomatico` dispara su reloj de dos minutos solo
/// `if (_hayRed != false && hayPendientes())`, y `hayPendientes` sale de
/// `ResumenPendientes.total`, que sumaba mutaciones, evidencias, datos,
/// movimientos de material y pedidos a bodega -- **pero no las incidencias**.
///
/// Así que al explicar una diferencia: se guardaba en `cola_incidencias`, la
/// cuenta daba cero, el reloj no enviaba nada, y el dato se quedaba en el
/// teléfono con señal perfecta hasta que el técnico tocara otra cosa o
/// apretara «Enviar ahora».
///
/// Y LO PEOR NO ERA ESO: la pantalla decía «0 cambios pendientes» teniendo
/// uno. Mostrar todo al día cuando no lo está es peor que no mostrar nada --
/// el técnico se va a su casa creyendo que entregó.
///
/// LO QUE SE PRUEBA es la cuenta y su consecuencia, no el envío en sí: el
/// envío ya tiene sus pruebas. Lo que fallaba era que nadie lo despertara.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_explicado_sube.db');

  setUpAll(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(),
          'pruebas_explicado_sube.db'),
    );
  });

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';

  late LocalDatabase db;

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    for (final t in const [
      'cola_incidencias',
      'cola_movimientos_material',
      'local_jornada',
      'local_kit',
    ]) {
      await base.delete(t);
    }
  });

  Future<void> explicar({String codigo = 'CON-SC-APC'}) => db.encolarIncidencia(
        id: 'inc-$codigo-${DateTime.now().microsecondsSinceEpoch}',
        orgId: orgA,
        profileId: perfilA,
        materialCodigo: codigo,
        materialNombre: 'Conector SC/APC',
        tipo: 'danado',
        cantidad: '3',
        motivo: 'Dañado: se partió al pelar el cable',
      );

  Future<ResumenPendientes> resumen() =>
      CicloDeVidaLocal(db).pendientesDe(orgId: orgA, profileId: perfilA);

  group('1. La cuenta de pendientes', () {
    test('Sin nada encolado, no hay pendientes', () async {
      //  El punto de partida: si esto se rompiera, la app diria que SIEMPRE
      //  hay algo que enviar y el reloj gastaria datos y bateria cada dos
      //  minutos, para nada.
      final r = await resumen();

      expect(r.hayPendientes, isFalse);
      expect(r.total, 0);
    });

    test('Una diferencia explicada CUENTA como pendiente', () async {
      //  EL DEFECTO. Antes del arreglo: total = 0 con la incidencia en cola.
      await explicar();
      final r = await resumen();

      expect(r.incidencias, 1);
      expect(r.total, 1);
      expect(r.hayPendientes, isTrue,
          reason: 'sin esto, el reloj del envio automatico nunca se despierta');
    });

    test('Y se NOMBRA, con el material: no como «1 cambio»', () async {
      //  Quien lo lee reconoce el conector que explico hace una hora, no un
      //  numero de filas. Mismo criterio que el resto de la hoja.
      await explicar();
      final r = await resumen();

      expect(r.detalle, isNotEmpty);
      expect(r.detalle.first, contains('Conector SC/APC'));
      expect(r.detalle.first, contains('Diferencia explicada'));
    });

    test('Dos explicaciones son dos pendientes', () async {
      await explicar(codigo: 'CON-SC-APC');
      await explicar(codigo: 'CABLE-DROP');
      final r = await resumen();

      expect(r.incidencias, 2);
      expect(r.total, 2);
    });

    test('Las de OTRO perfil no entran en mi cuenta', () async {
      await db.encolarIncidencia(
        id: 'inc-ajena', orgId: orgA, profileId: 'prof_otro',
        materialCodigo: 'X', materialNombre: 'X',
        tipo: 'danado', cantidad: '1', motivo: 'de otra persona',
      );
      final r = await resumen();

      expect(r.hayPendientes, isFalse);
    });
  });

  group('2. La consecuencia: el envio se despierta', () {
    test('Con señal y una diferencia explicada, el reloj ENVIA', () async {
      //  LA CADENA COMPLETA, que es lo que el usuario pidio: explicar algo y
      //  que suba solo, sin apretar nada.
      await explicar();
      final r = await resumen();

      int envios = 0;
      final auto = EnvioAutomatico(
        enviar: () async => envios++,
        hayPendientes: () => r.hayPendientes,
        cada: const Duration(milliseconds: 40),
        espera: const Duration(milliseconds: 10),
      );
      auto.alCambiarLaRed(true);
      auto.arrancar();
      await Future<void>.delayed(const Duration(milliseconds: 160));
      auto.parar();

      expect(envios, greaterThan(0),
          reason: 'con señal y algo pendiente, sube sin que nadie toque nada');
    });

    test('Sin nada pendiente NO envia: no gasta datos ni bateria', () async {
      //  El otro borde. Sin esto, "arreglar" el bug haciendo que
      //  `hayPendientes` devuelva siempre true pasaria la prueba de arriba.
      final r = await resumen();

      int envios = 0;
      final auto = EnvioAutomatico(
        enviar: () async => envios++,
        hayPendientes: () => r.hayPendientes,
        cada: const Duration(milliseconds: 40),
        espera: const Duration(milliseconds: 10),
      );
      auto.alCambiarLaRed(true);
      auto.arrancar();
      await Future<void>.delayed(const Duration(milliseconds: 160));
      auto.parar();

      //  Un envio es aceptable: el de «volvio la red», que no mira pendientes
      //  a proposito. Lo que no puede haber es el goteo del reloj.
      expect(envios, lessThanOrEqualTo(1));
    });
  });
}
