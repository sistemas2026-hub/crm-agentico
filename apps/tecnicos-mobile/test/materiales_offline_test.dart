import 'dart:io';

import 'package:campo/core/storage/ciclo_de_vida_local.dart';
import 'package:campo/core/storage/evidencia_storage_service.dart';
import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// El material que se gasta sin señal.
///
/// QUÉ CUIDAN ESTAS PRUEBAS
/// ------------------------
/// Que lo que el técnico gastó en la calle llegue al servidor **una vez**, y
/// que mientras no haya llegado no se pueda perder.
///
/// Las dos mitades importan por separado. Que llegue dos veces descuadra el
/// inventario de toda la empresa y nadie sabe por qué. Que no llegue deja al
/// inventario diciendo que el material sigue en la camioneta, y el faltante
/// aparece en un conteo físico tres meses después.
///
/// Por eso lo que se afirma acá es el efecto sobre los datos —cuántas filas
/// quedan, con qué estado, qué saldo se ve— y no que tal método se llamó.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  // Base propia: si compartiera archivo con otra suite, la preparación de
  // cada una le vaciaría las tablas a la otra.
  LocalDatabase.usarBaseDePruebas('pruebas_materiales_offline.db');

  const orgA = 'org_rapilink';
  const perfilA = 'prof_carlos';
  const orgB = 'org_conexiones';
  const perfilB = 'prof_pedro';

  late LocalDatabase localDb;
  late CicloDeVidaLocal ciclo;
  late Directory dirEvidencias;

  setUp(() async {
    localDb = LocalDatabase();
    ciclo = CicloDeVidaLocal(localDb);
    dirEvidencias = await Directory.systemTemp.createTemp('materiales_test_');
    EvidenciaStorageService.setOverrideDirectory(dirEvidencias);
    final db = await localDb.database;
    for (final t in const [
      'local_ordenes',
      'local_datos_dirty',
      'cola_mutaciones',
      'cola_evidencias',
      'local_kit',
      'cola_movimientos_material',
    ]) {
      await db.delete(t);
    }
  });

  tearDown(() async {
    EvidenciaStorageService.setOverrideDirectory(null);
    if (await dirEvidencias.exists()) {
      await dirEvidencias.delete(recursive: true);
    }
  });

  Future<void> darKit({
    String org = orgA,
    String perfil = perfilA,
    String codigo = 'CON-SC-APC',
    String nombre = 'Conector SC/APC',
    String disponible = '24',
  }) async {
    await localDb.reemplazarKit(
      orgId: org,
      profileId: perfil,
      materiales: <Map<String, dynamic>>[
        {
          'codigo': codigo,
          'nombre': nombre,
          'categoria': 'Conectividad',
          'clase': 'consumible',
          'unidad': 'unidades',
          'recibido': '24',
          'consumido': '0',
          'devuelto': '0',
          'disponible': disponible,
          'series': <String>[],
          'acta': 'K-2024-094',
        },
      ],
    );
  }

  Future<void> gastar({
    required String id,
    String org = orgA,
    String perfil = perfilA,
    String codigo = 'CON-SC-APC',
    String nombre = 'Conector SC/APC',
    String cantidad = '4',
    String tipo = 'consumo',
    String? ordenId,
    int? ordenNumero,
  }) async {
    await localDb.encolarMovimientoMaterial(
      id: id,
      orgId: org,
      profileId: perfil,
      materialCodigo: codigo,
      materialNombre: nombre,
      tipo: tipo,
      cantidad: cantidad,
      ordenId: ordenId,
      ordenNumero: ordenNumero,
    );
  }

  group('1. El movimiento se crea sin señal y queda a la espera', () {
    test('Queda pendiente, con su identidad y su hora de campo', () async {
      await gastar(id: 'mov-1');

      final cola = await localDb.getMovimientosMaterialPendientes(
        orgId: orgA, profileId: perfilA,
      );

      expect(cola, hasLength(1));
      expect(cola.first['estado'], 'pendiente');
      expect(cola.first['org_id'], orgA);
      expect(cola.first['profile_id'], perfilA);
      expect(cola.first['intentos'], 0);
      expect((cola.first['ocurrido_en'] as String).isNotEmpty, isTrue);
    });

    test('El saldo que se ve YA descuenta lo que no subió', () async {
      // Si no descontara, el técnico vería 24 conectores después de usar 4 y
      // se llevaría la sorpresa al llegar a la siguiente casa.
      await darKit();
      await gastar(id: 'mov-1', cantidad: '4');

      final saldo = await localDb.saldoLocalDe(
        orgId: orgA, profileId: perfilA, codigo: 'CON-SC-APC',
      );

      expect(saldo, 20);
    });

    test('Encolar dos veces el mismo id no duplica', () async {
      // La pantalla puede reintentar; el hecho es uno solo.
      await gastar(id: 'mov-1');
      await gastar(id: 'mov-1');

      final cola = await localDb.getMovimientosMaterialPendientes(
        orgId: orgA, profileId: perfilA,
      );
      expect(cola, hasLength(1));
    });
  });

  group('2. Sincronizar: pendiente → enviando → confirmado', () {
    test('Marcar en vuelo lo saca de la lista de por-enviar', () async {
      await gastar(id: 'mov-1');

      await localDb.marcarMovimientosEnviando(
        orgId: orgA, profileId: perfilA, ids: <String>['mov-1'],
      );

      final porEnviar = await localDb.getMovimientosMaterialPendientes(
        orgId: orgA, profileId: perfilA,
      );
      expect(porEnviar, isEmpty, reason: 'un segundo ciclo no lo reenvía');

      // Pero sigue contando como sin confirmar: todavía no llegó.
      final sinConfirmar = await localDb.getMovimientosMaterialSinConfirmar(
        orgId: orgA, profileId: perfilA,
      );
      expect(sinConfirmar, hasLength(1));
      expect(sinConfirmar.first['estado'], 'enviando');
    });

    test('Confirmado deja de estar pendiente y no se reenvía', () async {
      await gastar(id: 'mov-1');

      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA, resultado: 'aceptado',
      );

      expect(
        await localDb.getMovimientosMaterialPendientes(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
      );
      expect(
        await localDb.getMovimientosMaterialSinConfirmar(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
      );
    });

    test('Un fallo cuenta el intento y agenda el próximo', () async {
      await gastar(id: 'mov-1');
      final futuro = DateTime.now().millisecondsSinceEpoch + 60000;

      await localDb.registrarFalloMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA,
        nextAttemptAt: futuro, errorMensaje: 'El servidor respondio 503.',
      );

      // Antes de su turno no se reintenta: un error permanente no puede
      // gastar la batería de quien está trabajando.
      expect(
        await localDb.getMovimientosMaterialPendientes(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
      );
      // Llegado el turno, vuelve.
      final listos = await localDb.getMovimientosMaterialPendientes(
        orgId: orgA, profileId: perfilA, soloListosHasta: futuro + 1,
      );
      expect(listos, hasLength(1));
      expect(listos.first['intentos'], 1);
      expect(listos.first['estado'], 'error');
    });

    test('Un movimiento con error NUNCA se descarta solo', () async {
      await gastar(id: 'mov-1');
      for (var i = 0; i < 12; i++) {
        await localDb.registrarFalloMovimientoMaterial(
          id: 'mov-1', orgId: orgA, profileId: perfilA, nextAttemptAt: 0,
          errorMensaje: 'Fallo el envio.',
        );
      }

      final sinConfirmar = await localDb.getMovimientosMaterialSinConfirmar(
        orgId: orgA, profileId: perfilA,
      );
      expect(sinConfirmar, hasLength(1),
          reason: 'descartarlo es perder el único registro de que se usó');
      expect(sinConfirmar.first['intentos'], 12);
    });

    test('El error guardado no lleva secretos', () {
      // La columna sobrevive al cierre de sesión mientras haya pendientes: no
      // puede terminar ahí una URL firmada ni una cabecera de autorización.
      final mensaje = SyncQueueService.sanearError(
        Exception('Bearer eyJhbGciOi... https://firmada?X-Amz-Signature=abc'),
      );

      expect(mensaje, 'Fallo el envio.');
      expect(mensaje.toLowerCase(), isNot(contains('bearer')));
      expect(mensaje, isNot(contains('http')));
    });
  });

  group('3. El resultado del servidor no es el estado de envío', () {
    test('Un descuadre queda confirmado: subió, y no se reintenta', () async {
      await gastar(id: 'mov-1');

      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA,
        resultado: 'descuadre', motivo: 'Se registraron 30 y había 24.',
      );

      expect(
        await localDb.getMovimientosMaterialPendientes(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
        reason: 'reintentar un descuadre es pedirle al servidor que cambie de '
            'opinión',
      );
    });

    test('Pero sigue visible como novedad: no se resuelve en silencio', () async {
      await gastar(id: 'mov-1');
      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA,
        resultado: 'conflicto',
        motivo: 'La serie 48575448A9B0C1 ya figura instalada.',
      );

      final novedades = await localDb.getMovimientosMaterialConNovedad(
        orgId: orgA, profileId: perfilA,
      );

      expect(novedades, hasLength(1));
      expect(novedades.first['resultado'], 'conflicto');
      expect(novedades.first['motivo'], contains('48575448A9B0C1'));
    });

    test('Lo aceptado no aparece como novedad', () async {
      await gastar(id: 'mov-1');
      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA, resultado: 'aceptado',
      );

      expect(
        await localDb.getMovimientosMaterialConNovedad(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
      );
    });

    test('Y el saldo deja de descontarlo una vez confirmado', () async {
      // El kit que baja del servidor ya incluye el consumo: seguir restándolo
      // desde la cola lo contaría dos veces.
      await darKit(disponible: '20');
      await gastar(id: 'mov-1', cantidad: '4');
      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA, resultado: 'aceptado',
      );

      final saldo = await localDb.saldoLocalDe(
        orgId: orgA, profileId: perfilA, codigo: 'CON-SC-APC',
      );
      expect(saldo, 20);
    });
  });

  group('4. El lote parcial', () {
    test('Lo ya confirmado no se reenvía y lo nuevo sí', () async {
      await gastar(id: 'm1');
      await gastar(id: 'm2');
      await localDb.confirmarMovimientoMaterial(
        id: 'm1', orgId: orgA, profileId: perfilA, resultado: 'aceptado',
      );
      await gastar(id: 'm3');

      final porEnviar = await localDb.getMovimientosMaterialPendientes(
        orgId: orgA, profileId: perfilA,
      );

      expect(porEnviar.map((m) => m['id']).toSet(), <String>{'m2', 'm3'});
    });

    test('El orden de envío es el de ocurrencia', () async {
      // Importa para explicar un saldo: los consumos se aplican en el orden
      // en que pasaron, no en el que llegaron.
      await gastar(id: 'm1');
      await gastar(id: 'm2');
      await gastar(id: 'm3');

      final cola = await localDb.getMovimientosMaterialPendientes(
        orgId: orgA, profileId: perfilA,
      );

      expect(cola.map((m) => m['id']).toList(), <String>['m1', 'm2', 'm3']);
    });
  });

  group('5. Cada kit es de quien es', () {
    test('El técnico A no ve el kit del técnico B', () async {
      await darKit(perfil: perfilA);
      await darKit(perfil: perfilB, codigo: 'AJENO', nombre: 'Material ajeno');

      final deA = await localDb.getKit(orgId: orgA, profileId: perfilA);
      final deB = await localDb.getKit(orgId: orgA, profileId: perfilB);

      expect(deA.map((m) => m['codigo']), <String>['CON-SC-APC']);
      expect(deB.map((m) => m['codigo']), <String>['AJENO']);
    });

    test('La empresa A no ve el kit de la empresa B', () async {
      await darKit(org: orgA);
      await darKit(org: orgB, perfil: perfilB);

      expect(await localDb.getKit(orgId: orgB, profileId: perfilA), isEmpty);
    });

    test('Un movimiento ajeno no entra en mi cola ni en mi saldo', () async {
      await darKit();
      await gastar(id: 'ajeno', org: orgB, perfil: perfilB, cantidad: '99');

      expect(
        await localDb.getMovimientosMaterialPendientes(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
      );
      expect(
        await localDb.saldoLocalDe(
          orgId: orgA, profileId: perfilA, codigo: 'CON-SC-APC',
        ),
        24,
      );
    });

    test('Confirmar con la identidad equivocada no escribe nada', () async {
      await gastar(id: 'mov-1');

      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgB, profileId: perfilB, resultado: 'aceptado',
      );

      final mio = await localDb.getMovimientosMaterialSinConfirmar(
        orgId: orgA, profileId: perfilA,
      );
      expect(mio, hasLength(1));
      expect(mio.first['estado'], 'pendiente');
    });
  });

  group('6. Cerrar sesión con material sin subir', () {
    test('Cuenta como pendiente, igual que una fotografía', () async {
      await gastar(id: 'mov-1', ordenNumero: 4832);

      final pendientes = await ciclo.pendientesDe(
        orgId: orgA, profileId: perfilA,
      );

      expect(pendientes.hayPendientes, isTrue);
      expect(pendientes.movimientosDeMaterial, 1);
    });

    test('Se nombra con el material y la orden, no como "3 movimientos"', () async {
      await gastar(
        id: 'mov-1', nombre: 'Conector SC/APC', cantidad: '1', ordenNumero: 4832,
      );
      await gastar(
        id: 'mov-2', codigo: 'ONT-HG8145', nombre: 'ONT Huawei',
        cantidad: '1', ordenNumero: 4832,
      );

      final pendientes = await ciclo.pendientesDe(
        orgId: orgA, profileId: perfilA,
      );

      expect(pendientes.detalle, contains('OT #4832 · Conector SC/APC x1'));
      expect(pendientes.detalle, contains('OT #4832 · ONT Huawei x1'));
    });

    test('Con material sin subir NO se borra nada', () async {
      await darKit();
      await gastar(id: 'mov-1');

      final resultado = await ciclo.prepararPara(
        orgId: orgB, profileId: perfilB,
      );

      expect(resultado.hayTrabajoAjenoRetenido, isTrue);
      expect(
        await localDb.getMovimientosMaterialSinConfirmar(
          orgId: orgA, profileId: perfilA,
        ),
        hasLength(1),
      );
      expect(await localDb.getKit(orgId: orgA, profileId: perfilA), hasLength(1));
    });

    test('Sin nada sin subir, el kit sí se limpia', () async {
      await darKit();
      await gastar(id: 'mov-1');
      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA, resultado: 'aceptado',
      );

      await ciclo.purgarIdentidad(orgId: orgA, profileId: perfilA);

      expect(await localDb.getKit(orgId: orgA, profileId: perfilA), isEmpty);
      expect(
        await localDb.getMovimientosMaterialSinConfirmar(
          orgId: orgA, profileId: perfilA,
        ),
        isEmpty,
      );
    });

    test('Y quien entra después no ve el kit del anterior', () async {
      await darKit();
      await gastar(id: 'mov-1');
      await localDb.confirmarMovimientoMaterial(
        id: 'mov-1', orgId: orgA, profileId: perfilA, resultado: 'aceptado',
      );

      await ciclo.prepararPara(orgId: orgB, profileId: perfilB);

      expect(await localDb.getKit(orgId: orgA, profileId: perfilA), isEmpty);
      expect(await localDb.getKit(orgId: orgB, profileId: perfilB), isEmpty);
    });

    test('El material sigue la misma política que las evidencias', () async {
      // Las dos cosas son trabajo que solo existe en este teléfono. Que una
      // se conserve y la otra no sería una distinción que nadie puede
      // explicar.
      await gastar(id: 'mov-1');
      final soloMaterial = await ciclo.pendientesDe(
        orgId: orgA, profileId: perfilA,
      );

      expect(soloMaterial.hayPendientes, isTrue);
      expect(soloMaterial.evidencias, 0);
      expect(soloMaterial.movimientosDeMaterial, 1);
      expect(soloMaterial.total, 1);
    });
  });

  group('7. La aplicación puede actualizarse sin perder la jornada', () {
    test('La v9 agrega las tablas sin tocar lo que ya había', () async {
      // Una migración que recreara tablas se llevaría media jornada sin subir.
      await localDb.upsertOrden(
        orgId: orgA,
        profileId: perfilA,
        ordenData: <String, dynamic>{
          'id': 'ot-1',
          'numero': 4832,
          'estado': 'asignada',
          'cliente_nombre': 'María Fernández',
          'direccion': 'Cra 48',
          'tipo': <String, dynamic>{'nombre': 'FTTH', 'codigo': 'ftth'},
          'revision': 1,
        },
      );
      await gastar(id: 'mov-1');

      final db = await localDb.database;
      expect(await db.query('local_kit'), isEmpty);
      expect(await localDb.getOrdenes(orgId: orgA, profileId: perfilA),
          hasLength(1));
      expect(
        await localDb.getMovimientosMaterialSinConfirmar(
          orgId: orgA, profileId: perfilA,
        ),
        hasLength(1),
      );
    });
  });
}
