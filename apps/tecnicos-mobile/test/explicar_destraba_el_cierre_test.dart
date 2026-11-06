import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// EXPLICAR UNA DIFERENCIA DESTRABA EL CIERRE, SIN ESPERAR SEÑAL.
///
/// EL DEFECTO, REPORTADO EL 06/11/2026 POR QUIEN LO SUFRE
/// ------------------------------------------------------
/// «Para finalizar jornada toca reportar el material y sus cantidades, y al
/// aclarar todo finalizar. Pero se aclara el material y no deja presionar el
/// botón de cerrar jornada: toca dar al botón de sincronizar y así sí deja.»
///
/// La cadena: la explicación se guarda en `cola_incidencias`;
/// `EstadoDeJornada.leer` nunca consultaba esa tabla; `motivos` seguía siendo
/// la lista que mandó el servidor la última vez, y el servidor todavía no se
/// había enterado. Botón muerto hasta sincronizar.
///
/// `getIncidenciasSinConfirmar` YA EXISTÍA y la usaban solo las pruebas:
/// ningún código de producción la llamaba. Un método construido, probado y
/// sin llamador -- no daba error, daba un botón que no se podía apretar.
///
/// POR QUÉ IMPORTA MÁS DE LO QUE PARECE
/// ------------------------------------
/// `puedeCerrar` ya decía en su comentario: «La señal NO entra en esta
/// decisión... esperar a que se resuelva dejaría a alguien sin poder irse a su
/// casa». La intención estaba escrita y el código hacía lo contrario. En la
/// calle, sin señal, el técnico quedaba atrapado: había hecho todo lo que se
/// le pedía y la app no lo dejaba terminar.
///
/// EL MODO DE FALLA DEL ARREGLO ES SEGURO, y es a propósito: si el servidor
/// cambiara el texto de sus motivos, el descuento deja de encontrarlos y el
/// botón vuelve a bloquearse hasta sincronizar -- que es exactamente como
/// está hoy. Nunca al revés: nunca se habilita de más.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_explicar_cierre.db');

  setUpAll(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(),
          'pruebas_explicar_cierre.db'),
    );
  });

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';

  late LocalDatabase db;

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    for (final t in const [
      'local_kit',
      'cola_movimientos_material',
      'local_jornada',
      'cola_incidencias',
    ]) {
      await base.delete(t);
    }
  });

  //  LA FRASE EXACTA QUE ESCRIBE EL SERVIDOR, copiada de
  //  `campo/services/cierre_jornada.py::motivos_para_no_cerrar`:
  //      f"{material.nombre}: faltan {diferencia} {unidad} sin explicar."
  //  Si esa frase cambia allá, esta prueba se pone roja -- que es lo que se
  //  quiere: avisa que el descuento dejó de funcionar.
  const motivoDelServidor = 'Conector SC/APC: faltan 3 unidades sin explicar.';

  Map<String, dynamic> respuesta({
    List<String> motivos = const <String>[],
    String devuelto = '7',
  }) =>
      <String, dynamic>{
        'estado': 'pendiente',
        'puede_cerrar': motivos.isEmpty,
        'motivos': motivos,
        'series_sin_devolver': <String>[],
        'transferencias_pendientes': <Map<String, dynamic>>[],
        'resumen': <String, dynamic>{
          'ordenes': <String, dynamic>{
            'asignadas': 8, 'completadas': 8, 'pendientes': 0,
          },
          'material': <String, dynamic>{
            'recibido': '24', 'consumido': '14', 'a_devolver': '10',
            'devuelto': devuelto, 'diferencias': 1,
          },
          'detalle': <Map<String, dynamic>>[
            {
              'codigo': 'CON-SC-APC', 'nombre': 'Conector SC/APC',
              'unidad': 'unidades', 'esperado_devolver': '10',
              'devuelto': devuelto,
            },
          ],
        },
      };

  Future<EstadoDeJornada> leer() => EstadoDeJornada.leer(
        baseLocal: db,
        almacenamiento: _Sesion(orgA, perfilA),
      );

  Future<void> explicar({
    String codigo = 'CON-SC-APC',
    String nombre = 'Conector SC/APC',
    String motivo = 'Dañado: se partió el conector al pelar el cable',
  }) =>
      db.encolarIncidencia(
        id: 'inc-$codigo-${DateTime.now().microsecondsSinceEpoch}',
        orgId: orgA,
        profileId: perfilA,
        materialCodigo: codigo,
        materialNombre: nombre,
        tipo: 'danado',
        cantidad: '3',
        motivo: motivo,
      );

  group('1. El defecto reportado', () {
    test('Con la diferencia SIN explicar, no se puede cerrar', () async {
      //  El punto de partida: así tiene que seguir funcionando. Si esto se
      //  rompiera, el arreglo estaría dejando cerrar jornadas que no cuadran.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: const [motivoDelServidor]),
      );

      final estado = await leer();

      expect(estado.puedeCerrar, isFalse);
      expect(estado.motivosVigentes, contains(motivoDelServidor));
    });

    test('Al explicarla, el botón se habilita SIN sincronizar', () async {
      //  EL DEFECTO. Antes del arreglo: `puedeCerrar` seguía en false hasta
      //  darle a sincronizar.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: const [motivoDelServidor]),
      );

      await explicar();
      final estado = await leer();

      expect(estado.puedeCerrar, isTrue,
          reason: 'explicada la diferencia, no hay por qué esperar señal');
      expect(estado.motivosVigentes, isEmpty);
    });

    test('El motivo del servidor NO se borra: se marca resuelto', () async {
      //  La lista cruda se conserva. Perderla dejaría sin forma de saber qué
      //  había pedido el servidor cuando algo salga raro después.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: const [motivoDelServidor]),
      );

      await explicar();
      final estado = await leer();

      expect(estado.motivos, contains(motivoDelServidor),
          reason: 'lo que dijo el servidor se guarda tal cual');
      expect(estado.motivosVigentes, isEmpty,
          reason: 'pero ya no bloquea');
    });
  });

  group('2. Lo que NO destraba', () {
    test('Explicar un material NO tapa el motivo de OTRO', () async {
      //  El error caro: que aclarar una cosa destrabe todo. El técnico se
      //  iría a su casa con un faltante sin explicar que aparece en el conteo
      //  del mes que viene, sin nadie a quién preguntarle.
      const otro = 'Cable drop: faltan 20 metros sin explicar.';
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: const [motivoDelServidor, otro]),
      );

      await explicar();                       // solo el conector
      final estado = await leer();

      expect(estado.puedeCerrar, isFalse);
      expect(estado.motivosVigentes, orderedEquals(const <String>[otro]));
    });

    test('Un equipo sin ubicar NO se destraba explicando material', () async {
      //  Ese motivo no se resuelve con una explicación de faltante: hay que
      //  decir dónde está la serie. No se descuenta nunca.
      const serie = 'El equipo con serie ABC123 no se instaló ni volvió a '
          'bodega: hay que decir dónde está.';
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: const [serie]),
      );

      await explicar();
      final estado = await leer();

      expect(estado.puedeCerrar, isFalse);
      expect(estado.motivosVigentes, orderedEquals(const <String>[serie]));
    });

    test('Una incidencia de OTRO perfil no destraba la mía', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: respuesta(motivos: const [motivoDelServidor]),
      );

      await db.encolarIncidencia(
        id: 'inc-ajena', orgId: orgA, profileId: 'prof_otro',
        materialCodigo: 'CON-SC-APC', materialNombre: 'Conector SC/APC',
        tipo: 'danado', cantidad: '3', motivo: 'otra persona',
      );
      final estado = await leer();

      expect(estado.puedeCerrar, isFalse);
    });

    test('Una jornada ya cerrada sigue cerrada', () async {
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA,
        datos: <String, dynamic>{
          ...respuesta(motivos: const [motivoDelServidor]),
          'estado': 'confirmada',
        },
      );

      await explicar();
      final estado = await leer();

      expect(estado.puedeCerrar, isFalse,
          reason: 'explicar algo no reabre una jornada con acta congelada');
    });
  });

  group('3. Cuando sube de verdad', () {
    test('Confirmada la incidencia y sin motivos, sigue pudiendo cerrar',
        () async {
      //  Después de sincronizar: el servidor ya no manda el motivo y la
      //  incidencia queda confirmada. El resultado no puede cambiar.
      await db.guardarJornada(
        orgId: orgA, profileId: perfilA, datos: respuesta(),
      );

      final estado = await leer();

      expect(estado.puedeCerrar, isTrue);
      expect(estado.motivosVigentes, isEmpty);
    });
  });
}

class _Sesion implements SecureStorageLectura {
  _Sesion(this._org, this._perfil);

  final String _org;
  final String _perfil;

  @override
  Future<String?> getOrgId() async => _org;

  @override
  Future<String?> getProfileId() async => _perfil;
}
