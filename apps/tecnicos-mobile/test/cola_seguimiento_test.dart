import 'dart:convert';

import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' show join;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// La cola de reportes de seguimiento: lo que escribe el técnico sin señal.
///
/// LO QUE ESTE ARCHIVO DEFIENDE
/// ----------------------------
/// * **La clave de idempotencia es el `id` de la fila, y no cambia.** Es la
///   diferencia entre un reintento y un reporte nuevo. Si cada intento generara
///   una clave, el servidor contaría dos hechos donde hubo uno.
/// * **El orden se respeta.** Un AVANCE y después un CIERRE no se pueden subir
///   al revés: el servidor se niega a cerrar lo que nunca empezó.
/// * **Un rechazo de validación no se reintenta para siempre.** Reintentar algo
///   que el servidor no va a aceptar nunca es un bucle que gasta batería.
/// * **La hora de escritura se guarda al escribir, no al subir.** Es lo que
///   permite reconstruir la historia de un reporte hecho sin señal — y lo que
///   NO produce vencimientos, porque eso lo gobierna la llegada al servidor.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  LocalDatabase.usarBaseDePruebas('pruebas_cola_seguimiento.db');

  late LocalDatabase base;

  setUp(() async {
    LocalDatabase.resetForTesting();
    base = LocalDatabase();
  });

  tearDown(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(
        await databaseFactory.getDatabasesPath(),
        'pruebas_cola_seguimiento.db',
      ),
    );
  });

  Future<String> encolar({
    String momento = 'avance',
    Map<String, dynamic>? respuestas,
    bool requiereNoc = false,
    bool detener = true,
    DateTime? capturadoEn,
    String ordenId = 'ot-1',
  }) {
    return base.encolarSeguimiento(
      ordenId: ordenId,
      orgId: 'org-1',
      profileId: 'prof-1',
      momento: momento,
      respuestas: respuestas ?? <String, dynamic>{'validaciones': 'revisé todo'},
      requiereNoc: requiereNoc,
      detener: detener,
      capturadoEn: capturadoEn,
    );
  }

  group('1. La clave de idempotencia', () {
    test('encolar devuelve el id, que es la clave', () async {
      final String id = await encolar();

      expect(id, isNotEmpty);
      final pendientes = await base.seguimientosPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      expect(pendientes.length, 1);
      expect(pendientes.first['id'], id);
    });

    test('un error no cambia la clave: el reintento usa la misma', () async {
      final String id = await encolar();

      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'pendiente',
        mensaje: 'sin señal',
        esperarSegundos: 0,
      );

      final pendientes = await base.seguimientosPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      expect(pendientes.length, 1);
      expect(
        pendientes.first['id'],
        id,
        reason: 'Una clave nueva por intento es un identificador único, no una '
            'clave idempotente: el servidor contaría dos reportes.',
      );
      expect(pendientes.first['intentos'], 1);
    });

    test('dos reportes distintos del mismo momento no chocan', () async {
      final String uno = await encolar(
        capturadoEn: DateTime(2026, 10, 1, 8, 0),
      );
      final String otro = await encolar(
        capturadoEn: DateTime(2026, 10, 1, 9, 30),
      );

      expect(uno, isNot(otro));
      final pendientes = await base.seguimientosPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      expect(pendientes.length, 2);
    });
  });

  group('2. El orden de los hechos', () {
    test('se devuelven en el orden en que se escribieron', () async {
      await encolar(momento: 'inicio');
      await Future<void>.delayed(const Duration(milliseconds: 5));
      await encolar(momento: 'avance');
      await Future<void>.delayed(const Duration(milliseconds: 5));
      await encolar(momento: 'cierre');

      final pendientes = await base.seguimientosPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );

      expect(
        pendientes.map((Map<String, dynamic> f) => f['momento']).toList(),
        <String>['inicio', 'avance', 'cierre'],
        reason: 'El servidor se niega a cerrar lo que nunca empezó: subirlos al '
            'revés produciría un rechazo que es culpa del orden.',
      );
    });
  });

  group('3. Reintentar, o no', () {
    test('un rechazo de validación NO vuelve a la cola', () async {
      final String id = await encolar();

      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'error_validacion',
        mensaje: 'Falta el nivel inicial.',
        erroresPorCampo: <String, dynamic>{'nivel': 'Este campo es requerido.'},
      );

      final pendientes = await base.seguimientosPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      expect(
        pendientes,
        isEmpty,
        reason: 'Reintentar algo que el servidor no va a aceptar nunca es un '
            'bucle que gasta batería.',
      );
    });

    test('los errores por campo se guardan para mostrarlos donde van', () async {
      final String id = await encolar();
      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'error_validacion',
        mensaje: 'Falta el nivel inicial.',
        erroresPorCampo: <String, dynamic>{'nivel': 'Este campo es requerido.'},
      );

      final db = await base.database;
      final filas = await db.query(
        'cola_seguimiento',
        where: 'id = ?',
        whereArgs: [id],
      );
      final Object? crudo = filas.first['errores_json'];
      final Map<String, dynamic> errores =
          Map<String, dynamic>.from(jsonDecode(crudo! as String) as Map);

      expect(errores['nivel'], 'Este campo es requerido.');
      expect(filas.first['error_mensaje'], 'Falta el nivel inicial.');
    });

    test('un fallo de red sí vuelve, pero no inmediatamente', () async {
      final String id = await encolar();

      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'pendiente',
        mensaje: 'sin señal',
      );

      // Con la espera por defecto todavía no toca: no se reintenta en bucle.
      final ahora = await base.seguimientosPendientes(
        orgId: 'org-1',
        profileId: 'prof-1',
      );
      expect(ahora, isEmpty);

      // Pero sigue en la cola, esperando.
      expect(
        await base.contarSeguimientosPendientes(
          orgId: 'org-1',
          profileId: 'prof-1',
        ),
        1,
        reason: 'Esperar no es perder: el reporte sigue ahí.',
      );
    });

    test('la espera crece con los intentos', () async {
      final String id = await encolar();
      final db = await base.database;

      int esperaDe(List<Map<String, Object?>> filas) =>
          (filas.first['next_attempt_at'] as int) -
          DateTime.now().millisecondsSinceEpoch;

      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'pendiente',
        mensaje: 'x',
      );
      final primera = esperaDe(
        await db.query('cola_seguimiento', where: 'id = ?', whereArgs: [id]),
      );

      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'pendiente',
        mensaje: 'x',
      );
      final segunda = esperaDe(
        await db.query('cola_seguimiento', where: 'id = ?', whereArgs: [id]),
      );

      expect(
        segunda,
        greaterThan(primera),
        reason: 'Sin espera creciente, un servidor caído recibe un reporte por '
            'segundo desde cada teléfono.',
      );
    });

    test('subido deja de estar pendiente y limpia el error anterior', () async {
      final String id = await encolar();
      await base.marcarSeguimientoConError(
        id: id,
        estadoFinal: 'pendiente',
        mensaje: 'sin señal',
        esperarSegundos: 0,
      );
      await base.marcarSeguimientoSubido(id);

      expect(
        await base.contarSeguimientosPendientes(
          orgId: 'org-1',
          profileId: 'prof-1',
        ),
        0,
      );

      final db = await base.database;
      final fila = (await db.query(
        'cola_seguimiento',
        where: 'id = ?',
        whereArgs: [id],
      ))
          .first;
      expect(fila['estado'], 'sincronizado');
      expect(fila['error_mensaje'], isNull);
      expect(fila['confirmado_en'], isNotNull);
    });
  });

  group('4. La hora de escritura', () {
    test('se guarda la que se le pasa, no la de subida', () async {
      final DateTime cuando = DateTime(2026, 10, 1, 8, 0);
      final String id = await encolar(capturadoEn: cuando);

      final db = await base.database;
      final fila = (await db.query(
        'cola_seguimiento',
        where: 'id = ?',
        whereArgs: [id],
      ))
          .first;

      final DateTime guardada =
          DateTime.parse(fila['capturado_en_dispositivo']! as String);
      expect(
        guardada.toUtc(),
        cuando.toUtc(),
        reason: 'Es la hora en que el técnico escribió el reporte, que puede '
            'ser una hora antes de que haya señal.',
      );
    });

    test('sin hora explícita toma la de ahora', () async {
      final DateTime antes = DateTime.now().toUtc();
      final String id = await encolar();

      final db = await base.database;
      final fila = (await db.query(
        'cola_seguimiento',
        where: 'id = ?',
        whereArgs: [id],
      ))
          .first;
      final DateTime guardada =
          DateTime.parse(fila['capturado_en_dispositivo']! as String).toUtc();

      expect(
        guardada.isBefore(antes.subtract(const Duration(seconds: 2))),
        isFalse,
      );
    });
  });

  group('5. Lo propio de un bloqueo', () {
    test('requiere_noc y detener se guardan como los dos datos que son',
        () async {
      final String id = await encolar(
        momento: 'bloqueo',
        respuestas: <String, dynamic>{'motivo': 'sin acceso al poste'},
        requiereNoc: true,
        detener: false,
      );

      final db = await base.database;
      final fila = (await db.query(
        'cola_seguimiento',
        where: 'id = ?',
        whereArgs: [id],
      ))
          .first;

      // Dos conceptos distintos: estar detenido y necesitar al NOC. Es la
      // decisión que el CRM ya tomó, y la app no la reinterpreta.
      expect(fila['requiere_noc'], 1);
      expect(fila['detener'], 0);
    });

    test('por defecto un bloqueo detiene y no es del NOC', () async {
      final String id = await encolar(momento: 'bloqueo');

      final db = await base.database;
      final fila = (await db.query(
        'cola_seguimiento',
        where: 'id = ?',
        whereArgs: [id],
      ))
          .first;

      expect(fila['detener'], 1);
      expect(fila['requiere_noc'], 0);
    });
  });

  group('6. Aislamiento', () {
    test('otra empresa no ve los reportes pendientes', () async {
      await encolar();

      expect(
        await base.seguimientosPendientes(orgId: 'org-2', profileId: 'prof-1'),
        isEmpty,
      );
      expect(
        await base.contarSeguimientosPendientes(
          orgId: 'org-2',
          profileId: 'prof-1',
        ),
        0,
      );
    });

    test('otra persona de la misma empresa tampoco', () async {
      await encolar();

      expect(
        await base.seguimientosPendientes(orgId: 'org-1', profileId: 'prof-2'),
        isEmpty,
      );
    });
  });
}
