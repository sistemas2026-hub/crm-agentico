
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';
import 'package:campo/features/inicio/resumen_de_inicio.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

/// El día completo, contra la base de verdad.
///
/// POR QUÉ ESTE ARCHIVO ES DISTINTO A TODOS LOS DEMÁS
/// --------------------------------------------------
/// Hasta acá cada pantalla se probó sola, con su fuente inyectada: se verificó
/// que **dibuja bien lo que recibe**. Eso deja una pregunta sin contestar, que
/// es la que de verdad importa en una aplicación offline:
///
///     ¿el dato que alguien genera en un paso aparece donde tiene que
///     aparecer en el siguiente?
///
/// Un consumo registrado dentro de una orden tiene que bajar el saldo en
/// Materiales y cambiar lo que se espera devolver en el cierre de jornada.
/// Las tres pantallas leen de lugares distintos —`DatosDeEjecucion`,
/// `KitDeJornada`, `EstadoDeJornada`— y cada una podría estar bien por su
/// cuenta mientras el conjunto miente.
///
/// Por eso acá no hay fixtures por pantalla: hay **una sola base**, y cada
/// paso lee lo que dejó el anterior. Es la diferencia entre "cada pieza anda"
/// y "el día del técnico cierra".
///
/// SIN WIDGETS, A PROPÓSITO
/// ------------------------
/// Lo que se prueba es el viaje del dato, no el dibujo — eso ya lo cubren la
/// matriz de estados y las capturas. Además, mezclar FFI con pruebas de widget
/// en un mismo archivo colgó esta suite una vez.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_flujo_jornada.db');

  const String org = 'org_rapilink';
  const String carlos = 'prof_carlos';
  const String pedro = 'prof_pedro';
  const String ot = 'ot-4832';

  late LocalDatabase db;

  setUpAll(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(), 'pruebas_flujo_jornada.db'),
    );
  });

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    for (final String t in const <String>[
      'local_ordenes',
      'local_kit',
      'cola_movimientos_material',
      'local_jornada',
      'cola_incidencias',
    ]) {
      await base.delete(t);
    }
  });

  // --- El estado inicial del día -------------------------------------------

  /// La orden que el despacho asignó, con su plantilla.
  Future<void> sembrarOrden({String perfil = carlos}) => db.upsertOrden(
        orgId: org,
        profileId: perfil,
        ordenData: <String, dynamic>{
          'id': ot,
          'numero': 4832,
          'estado': 'en_sitio',
          'cliente_nombre': 'Carlos Gómez Rincón',
          'direccion': 'Cra 45 #12-88',
          'telefono': '3001234567',
          'revision': 7,
          'tipo': <String, dynamic>{
            'nombre': 'Instalación FTTH',
            'codigo': 'ftth_instalacion',
            'schema_version': 1,
          },
          'schema': <String, dynamic>{
            'campos': FuenteDeEjecucionFalsa.camposTipicos,
            'evidencias': FuenteDeEjecucionFalsa.requisitosTipicos,
          },
        },
      );

  /// El kit que la bodega entregó: diez conectores, nada usado.
  Future<void> sembrarKit({String perfil = carlos}) => db.reemplazarKit(
        orgId: org,
        profileId: perfil,
        materiales: <Map<String, dynamic>>[
          <String, dynamic>{
            'codigo': 'CON-SC-APC',
            'nombre': 'Conector SC/APC',
            'categoria': 'Conectividad',
            'clase': 'consumible',
            'unidad': 'unidades',
            'recibido': '10',
            'consumido': '0',
            'devuelto': '0',
            'acta': 'Acta #K-2026-311',
          },
        ],
      );

  /// El espejo de la jornada, como lo calcula el servidor.
  Future<void> sembrarJornada({
    String perfil = carlos,
    String consumido = '0',
    String aDevolver = '10',
    String estado = 'pendiente',
    List<String> motivos = const <String>[],
  }) =>
      db.guardarJornada(
        orgId: org,
        profileId: perfil,
        datos: <String, dynamic>{
          'estado': estado,
          'puede_cerrar': motivos.isEmpty,
          'motivos': motivos,
          'series_sin_devolver': <String>[],
          'transferencias_pendientes': <Map<String, dynamic>>[],
          'resumen': <String, dynamic>{
            'ordenes': <String, dynamic>{
              'asignadas': 1,
              'completadas': 0,
              'pendientes': 1,
            },
            'material': <String, dynamic>{
              'recibido': '10',
              'consumido': consumido,
              'a_devolver': aDevolver,
              'devuelto': '0',
              'diferencias': 0,
            },
            'detalle': <Map<String, dynamic>>[
              <String, dynamic>{
                'codigo': 'CON-SC-APC',
                'nombre': 'Conector SC/APC',
                'unidad': 'unidades',
                'esperado_devolver': aDevolver,
                'devuelto': '0',
              },
            ],
          },
        },
      );

  SecureStorageLectura sesion(String perfil) => _Sesion(org, perfil);

  FuenteLocalDeEjecucion ejecucionDe(String perfil) => FuenteLocalDeEjecucion(
        baseLocal: db,
        almacenamiento: sesion(perfil),
      );

  Future<KitDeJornada> kitDe(String perfil) => KitDeJornada.leer(
        baseLocal: db,
        almacenamiento: sesion(perfil),
      );

  Future<EstadoDeJornada> jornadaDe(String perfil) => EstadoDeJornada.leer(
        baseLocal: db,
        almacenamiento: sesion(perfil),
      );

  /// Lo que ve Inicio: se arma con las órdenes de la base y la jornada.
  Future<ResumenDeInicio> inicioDe(String perfil) async {
    final List<Map<String, dynamic>> filas =
        await db.getOrdenes(orgId: org, profileId: perfil);
    final EstadoDeJornada dia = await jornadaDe(perfil);
    return ResumenDeInicio.armar(
      trabajos: <TrabajoVista>[
        for (final Map<String, dynamic> f in filas) TrabajoVista.desdeOrden(f),
      ],
      jornada: dia,
      movimientosSinSubir: dia.sinSubir,
      ahora: DateTime(2026, 9, 22, 10, 0),
    );
  }

  /// Registrar consumo de material contra una orden, como lo hace la pantalla.
  Future<void> consumir({
    required String id,
    required String cantidad,
    String perfil = carlos,
    String serie = '',
  }) =>
      db.encolarMovimientoMaterial(
        id: id,
        orgId: org,
        profileId: perfil,
        materialCodigo: 'CON-SC-APC',
        materialNombre: 'Conector SC/APC',
        tipo: 'consumo',
        cantidad: cantidad,
        serie: serie,
        ordenId: ot,
        ordenNumero: 4832,
      );

  group('1. El día arranca con lo que el despacho dejó', () {
    test('Inicio ve la orden y el kit de la jornada', () async {
      await sembrarOrden();
      await sembrarKit();
      await sembrarJornada();

      final ResumenDeInicio inicio = await inicioDe(carlos);

      expect(inicio.totalDeTrabajos, 1);
      expect(inicio.siguiente?.numero, 4832);
      expect(inicio.hayKit, isTrue);
      expect(inicio.kitDisponible, '10');
      expect(inicio.hayProblemas, isFalse);
    });

    test('Y la ejecución abre esa misma orden con su plantilla', () async {
      await sembrarOrden();

      final DatosDeEjecucion? datos = await ejecucionDe(carlos).cargar(ot);

      expect(datos, isNotNull);
      expect(datos!.numeroDeOrden, 4832);
      expect(datos.revision, 7);
      expect(datos.campos, hasLength(4));
    });
  });

  group('2. Lo que se responde queda, aunque se cierre la pantalla', () {
    test('Un campo guardado se lee de vuelta al reabrir', () async {
      await sembrarOrden();
      final FuenteLocalDeEjecucion fuente = ejecucionDe(carlos);

      await fuente.guardarCampo(
        orgId: org,
        profileId: carlos,
        ordenId: ot,
        clave: 'potencia_rx',
        valor: '-18.4',
      );

      // "Cerrar y volver a abrir" es exactamente esto: una carga nueva.
      final DatosDeEjecucion otraVez = (await fuente.cargar(ot))!;

      expect(otraVez.valores['potencia_rx'], '-18.4');
      expect(
        otraVez.camposObligatoriosSinLlenar,
        isNot(contains('Potencia óptica en roseta del cliente')),
      );
    });
  });

  group('3. Un consumo viaja hasta las tres pantallas', () {
    test('Registrado en la OT, se ve en Materiales y en la Jornada', () async {
      // El corazón de la prueba: el mismo movimiento, leído por tres clases
      // distintas que alimentan tres pantallas distintas.
      await sembrarOrden();
      await sembrarKit();
      await sembrarJornada();

      await consumir(id: 'mov-1', cantidad: '2');

      // --- Materiales: el saldo baja al instante, sin esperar al servidor.
      final KitDeJornada kit = await kitDe(carlos);
      final MaterialEnCustodia conector = kit.materiales.single;
      expect(conector.usados, 2);
      expect(conector.disponibles, 8,
          reason: 'diez recibidos menos dos consumidos');
      expect(kit.sinSubir, 1, reason: 'todavía no salió del teléfono');

      // --- Ejecución: el consumo aparece asociado a su orden.
      final DatosDeEjecucion datos = (await ejecucionDe(carlos).cargar(ot))!;
      expect(datos.materialesUsados, hasLength(1));
      expect(datos.materialesUsados.single['material_codigo'], 'CON-SC-APC');
      expect(datos.materialesUsados.single['cantidad'], '2');

      // --- Jornada: lo cuenta como pendiente de subir.
      final EstadoDeJornada dia = await jornadaDe(carlos);
      expect(dia.sinSubir, 1);

      // --- Inicio: lo avisa, y en gravedad media: sube solo.
      //
      // `single` no: a media jornada el espejo del servidor todavia dice que
      // se esperan devolver diez y van cero devueltos, asi que ademas hay un
      // aviso de diferencia. Los dos son legitimos; lo que se mide aca es que
      // lo que espera senal no se pinte como alarma.
      final ResumenDeInicio inicio = await inicioDe(carlos);
      expect(inicio.hayProblemas, isTrue);
      final AvisoDeInicio sinEnviar = inicio.avisos.firstWhere(
        (AvisoDeInicio a) => a.titulo.contains('sin enviar'),
      );
      expect(sinEnviar.gravedad, GravedadDeAviso.media);
    });

    test('Dos consumos se suman; no se pisan', () async {
      await sembrarKit();

      await consumir(id: 'mov-1', cantidad: '2');
      await consumir(id: 'mov-2', cantidad: '3');

      final KitDeJornada kit = await kitDe(carlos);
      expect(kit.materiales.single.usados, 5);
      expect(kit.materiales.single.disponibles, 5);
      expect(kit.sinSubir, 2);
    });

    test('El mismo movimiento dos veces cuenta una sola', () async {
      // Idempotencia: un toque doble, o un reintento de la pantalla, no puede
      // descontar el material dos veces.
      await sembrarKit();

      await consumir(id: 'mov-1', cantidad: '2');
      await consumir(id: 'mov-1', cantidad: '2');

      final KitDeJornada kit = await kitDe(carlos);
      expect(kit.materiales.single.usados, 2, reason: 'una sola vez');
      expect(kit.sinSubir, 1);
    });
  });

  group('4. Sin señal el día sigue, y al volver se ordena', () {
    test('Se registra sin red y queda esperando turno', () async {
      await sembrarKit();
      await sembrarJornada();

      await consumir(id: 'mov-1', cantidad: '2');

      expect((await kitDe(carlos)).sinSubir, 1);
      expect((await jornadaDe(carlos)).sinSubir, 1);
      // Y el saldo ya refleja el consumo: no se espera al servidor para
      // mostrar lo que el técnico acaba de hacer.
      expect((await kitDe(carlos)).materiales.single.disponibles, 8);
    });

    test('Cuando sube, deja de estar pendiente y el saldo no cambia',
        () async {
      await sembrarKit();
      await consumir(id: 'mov-1', cantidad: '2');

      await db.confirmarMovimientoMaterial(
        id: 'mov-1',
        orgId: org,
        profileId: carlos,
        resultado: 'aceptado',
      );

      final KitDeJornada kit = await kitDe(carlos);
      expect(kit.sinSubir, 0, reason: 'ya llegó al servidor');
      expect(
        kit.materiales.single.disponibles,
        8,
        reason: 'el saldo es el mismo antes y después de subir: si cambiara, '
            'el técnico vería moverse un número que él no tocó',
      );
      expect(kit.conNovedad, isEmpty);
    });

    test('Un fallo de red no descarta el movimiento', () async {
      await sembrarKit();
      await consumir(id: 'mov-1', cantidad: '2');

      await db.registrarFalloMovimientoMaterial(
        id: 'mov-1',
        orgId: org,
        profileId: carlos,
        nextAttemptAt: 0,
        errorMensaje: 'El servidor respondió 503.',
      );

      final KitDeJornada kit = await kitDe(carlos);
      expect(kit.sinSubir, 1, reason: 'sigue en la cola');
      expect(kit.materiales.single.disponibles, 8);
    });
  });

  group('5. Lo que el servidor objeta llega hasta la pantalla', () {
    test('Un descuadre vuelve como novedad, con su motivo', () async {
      await sembrarKit();
      await consumir(id: 'mov-1', cantidad: '2');

      await db.confirmarMovimientoMaterial(
        id: 'mov-1',
        orgId: org,
        profileId: carlos,
        resultado: 'descuadre',
        motivo: 'El saldo no coincide con lo que registró bodega.',
      );

      final KitDeJornada kit = await kitDe(carlos);
      expect(kit.conNovedad, hasLength(1));
      expect(kit.conNovedad.single.resultado, 'descuadre');
      expect(kit.conNovedad.single.titulo, 'No cuadra con el kit');
      expect(kit.conNovedad.single.esDeIdentidad, isFalse);
      expect(kit.conNovedad.single.queHacer, contains('Explicá qué pasó'));
    });

    test('Un conflicto de serial llega con la serie y otro camino', () async {
      await sembrarKit();
      await consumir(id: 'mov-2', cantidad: '1', serie: '48575443-A190C');

      await db.confirmarMovimientoMaterial(
        id: 'mov-2',
        orgId: org,
        profileId: carlos,
        resultado: 'conflicto',
        motivo: 'Ya figura instalada en la OT #4720.',
      );

      final MovimientoConNovedad novedad =
          (await kitDe(carlos)).conNovedad.single;

      expect(novedad.esDeIdentidad, isTrue);
      expect(novedad.serie, '48575443-A190C',
          reason: 'la serie es lo que distingue este problema del otro');
      expect(novedad.queHacer, contains('supervisor'));
      expect(novedad.queHacer, isNot(contains('Explicá')));
    });
  });

  group('6. El cierre refleja lo que pasó, no lo que se esperaba', () {
    test('Con una diferencia sin explicar no se puede cerrar', () async {
      await sembrarKit();
      await sembrarJornada(
        consumido: '2',
        aDevolver: '8',
        motivos: <String>['Conector SC/APC: faltan 2 unidades sin explicar.'],
      );

      final EstadoDeJornada dia = await jornadaDe(carlos);

      expect(dia.puedeCerrar, isFalse);
      expect(dia.motivos, isNotEmpty);
    });

    test('Explicada, el servidor deja de objetarla', () async {
      await sembrarKit();
      await sembrarJornada(
        consumido: '2',
        aDevolver: '8',
        motivos: <String>['faltan 2 sin explicar'],
      );

      await db.encolarIncidencia(
        id: 'inc-1',
        orgId: org,
        profileId: carlos,
        materialCodigo: 'CON-SC-APC',
        tipo: 'perdido',
        cantidad: '2',
        motivo: 'Perdido: se cayeron de la escalera.',
      );
      // La siguiente sincronización baja la jornada recalculada.
      await sembrarJornada(consumido: '2', aDevolver: '8');

      expect((await jornadaDe(carlos)).puedeCerrar, isTrue);
    });

    test('Tomar el cierre no es tenerlo cerrado', () async {
      await sembrarKit();
      await sembrarJornada(consumido: '2', aDevolver: '8');

      await db.marcarCierreLocal(
        orgId: org,
        profileId: carlos,
        clave: 'cierre-1',
      );
      final EstadoDeJornada tomada = await jornadaDe(carlos);

      expect(tomada.cierreTomado, isTrue);
      expect(tomada.cerrada, isFalse,
          reason: 'irse a casa creyendo que entregó es el peor final posible');
      expect(tomada.puedeCerrar, isFalse, reason: 'no se cierra dos veces');

      // El servidor confirma y recién ahí queda cerrada.
      await sembrarJornada(
        consumido: '2',
        aDevolver: '8',
        estado: 'confirmada',
      );
      expect((await jornadaDe(carlos)).cerrada, isTrue);
    });

    test('Se puede cerrar con cosas sin subir: la red no decide esto',
        () async {
      await sembrarKit();
      await sembrarJornada(consumido: '2', aDevolver: '8');
      await consumir(id: 'mov-1', cantidad: '1');

      final EstadoDeJornada dia = await jornadaDe(carlos);

      expect(dia.sinSubir, 1);
      expect(dia.puedeCerrar, isTrue,
          reason: 'esperar señal para poder irse a casa no es una opción');
    });
  });

  group('7. Nada de esto se mezcla entre personas', () {
    test('El consumo de uno no toca el kit del otro', () async {
      await sembrarKit();
      await sembrarKit(perfil: pedro);

      await consumir(id: 'mov-1', cantidad: '2');

      expect((await kitDe(carlos)).materiales.single.disponibles, 8);
      expect(
        (await kitDe(pedro)).materiales.single.disponibles,
        10,
        reason: 'el material de Pedro no se movió',
      );
      expect((await kitDe(pedro)).sinSubir, 0);
    });

    test('Y la orden de uno no aparece en el inicio del otro', () async {
      await sembrarOrden();
      await sembrarJornada();

      expect((await inicioDe(carlos)).totalDeTrabajos, 1);
      expect((await inicioDe(pedro)).totalDeTrabajos, 0);
    });

    test('Confirmar con la identidad equivocada no escribe nada', () async {
      await sembrarKit();
      await consumir(id: 'mov-1', cantidad: '2');

      await db.confirmarMovimientoMaterial(
        id: 'mov-1',
        orgId: org,
        profileId: pedro,
        resultado: 'aceptado',
      );

      expect(
        (await kitDe(carlos)).sinSubir,
        1,
        reason: 'sigue siendo de Carlos y sigue sin confirmar',
      );
    });
  });

  group('8. El día entero, de una sola pasada', () {
    test('De la jornada abierta al acta, sin contradicciones', () async {
      // Lo que hace alguien un martes, en orden, leyendo cada vez lo que la
      // pantalla correspondiente leería.
      await sembrarOrden();
      await sembrarKit();
      await sembrarJornada();

      // 1. Abre la aplicación: tiene un trabajo y su kit completo.
      final ResumenDeInicio alEmpezar = await inicioDe(carlos);
      expect(alEmpezar.siguiente?.numero, 4832);
      expect(alEmpezar.kitDisponible, '10');

      // 2. Entra a la orden y responde el formulario.
      final FuenteLocalDeEjecucion fuente = ejecucionDe(carlos);
      await fuente.guardarCampo(
        orgId: org,
        profileId: carlos,
        ordenId: ot,
        clave: 'potencia_rx',
        valor: '-18.4',
      );
      await fuente.guardarCampo(
        orgId: org,
        profileId: carlos,
        ordenId: ot,
        clave: 'tipo_intervencion',
        valor: 'Roseta / Conector',
      );

      // 3. Usa material. Sin señal: queda en la cola.
      await consumir(id: 'mov-dia', cantidad: '2');

      // 4. Vuelve a Materiales: el saldo ya bajó.
      expect((await kitDe(carlos)).materiales.single.disponibles, 8);

      // 5. Cierra la orden y la vuelve a abrir: todo sigue ahí.
      final DatosDeEjecucion reabierta = (await fuente.cargar(ot))!;
      expect(reabierta.valores['potencia_rx'], '-18.4');
      expect(reabierta.materialesUsados, hasLength(1));
      expect(reabierta.camposObligatoriosSinLlenar, isEmpty,
          reason: 'los dos obligatorios están respondidos');

      // 6. Vuelve la señal: el movimiento sube.
      await db.confirmarMovimientoMaterial(
        id: 'mov-dia',
        orgId: org,
        profileId: carlos,
        resultado: 'aceptado',
      );
      expect((await kitDe(carlos)).sinSubir, 0);
      expect((await kitDe(carlos)).materiales.single.disponibles, 8,
          reason: 'subir no cambia el saldo');

      // 7. El servidor recalcula la jornada con ese consumo.
      await sembrarJornada(consumido: '2', aDevolver: '8');
      final EstadoDeJornada antesDeCerrar = await jornadaDe(carlos);
      expect(antesDeCerrar.consumido, '2');
      expect(antesDeCerrar.aDevolver, '8');
      expect(antesDeCerrar.puedeCerrar, isTrue);

      // 8. Toma el cierre y se va. El acta la confirma el servidor.
      await db.marcarCierreLocal(
        orgId: org,
        profileId: carlos,
        clave: 'cierre-dia',
      );
      expect((await jornadaDe(carlos)).cierreTomado, isTrue);
      expect((await jornadaDe(carlos)).cerrada, isFalse);

      await sembrarJornada(
        consumido: '2',
        aDevolver: '8',
        estado: 'confirmada',
      );
      final EstadoDeJornada cerrada = await jornadaDe(carlos);
      expect(cerrada.cerrada, isTrue);

      // 9. Y el número del acta coincide con lo que el técnico hizo: dos
      //    conectores, ni uno más.
      expect(cerrada.consumido, '2');
      expect((await kitDe(carlos)).materiales.single.usados, 2);
    });
  });
}

/// Una sesión fija, sin tocar el almacenamiento seguro del sistema.
class _Sesion implements SecureStorageLectura {
  _Sesion(this._org, this._perfil);

  final String? _org;
  final String? _perfil;

  @override
  Future<String?> getOrgId() async => _org;

  @override
  Future<String?> getProfileId() async => _perfil;
}
