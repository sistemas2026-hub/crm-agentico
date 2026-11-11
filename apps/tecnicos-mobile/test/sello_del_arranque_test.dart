import 'package:campo/core/storage/local_database.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// Con cuántas órdenes arrancó el día, sellado contra SQLite real.
///
/// QUÉ CUIDA ESTE ARCHIVO
/// ----------------------
/// La pantalla decía «2 asignadas · arrancó con 38»: el 38 era el historial
/// descargado. El número se intentó derivar tres veces de la lista y las tres
/// dependían de un dato que puede faltar —la fecha de cierre de una orden que
/// se acaba de cerrar—, así que se retiró en vez de adivinar.
///
/// El sello lo convierte en un hecho, y lo que estas pruebas afirman es la
/// regla que lo hace confiable: **solo sube**. Esa no es prudencia, es el
/// arreglo: la orden que por unos segundos no está ni en las abiertas ni en
/// las cerradas de hoy ya se contó cuando estaba abierta.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  // Base propia: compartir archivo con otra suite deja que la preparación de
  // una le vacíe las tablas a la otra.
  LocalDatabase.usarBaseDePruebas('pruebas_sello_arranque.db');

  const String orgA = 'org_rapilink';
  const String perfilA = 'prof_carlos';
  const String perfilB = 'prof_pedro';
  const String orgB = 'org_conexiones';

  final DateTime manana = DateTime(2026, 11, 11, 7, 10);
  final DateTime tarde = DateTime(2026, 11, 11, 16, 40);
  final DateTime otroDia = DateTime(2026, 11, 12, 7, 5);

  late LocalDatabase db;

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    await base.delete('local_arranque_del_dia');
  });

  group('la regla del sello', () {
    test('el primer sello del día es lo que se cuenta', () async {
      final int sello = await db.sellarArranqueDelDia(
        orgId: orgA,
        profileId: perfilA,
        trabajoDelDia: 7,
        ahora: manana,
      );

      expect(sello, 7);
      expect(
        await db.arranqueDelDia(
            orgId: orgA, profileId: perfilA, ahora: manana),
        7,
      );
    });

    test('NO BAJA cuando el conteo baja, y eso es el arreglo', () async {
      // El caso medido: una orden cerrada hace un minuto todavía no trae su
      // fecha de cierre, así que por unos segundos no está ni en las abiertas
      // ni en las cerradas de hoy. Sin esta regla el día «arrancaría con 6».
      await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 7, ahora: manana);

      final int sello = await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 6, ahora: tarde);

      expect(sello, 7, reason: 'esa orden ya se contó cuando estaba abierta');
    });

    test('SUBE cuando el despacho agrega una orden a media mañana', () async {
      await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 7, ahora: manana);

      final int sello = await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 9, ahora: tarde);

      expect(sello, 9, reason: 'el día terminó teniendo esas dos órdenes más');
    });

    test('cada día tiene su propio sello', () async {
      await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 7, ahora: manana);

      final int hoy = await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 3, ahora: otroDia);

      expect(hoy, 3, reason: 'el sello de ayer no es el piso de hoy');
      expect(
        await db.arranqueDelDia(
            orgId: orgA, profileId: perfilA, ahora: manana),
        7,
        reason: 'y el de ayer sigue donde estaba',
      );
    });

    test('un sello de cero se distingue de no tener sello', () async {
      expect(
        await db.arranqueDelDia(
            orgId: orgA, profileId: perfilA, ahora: manana),
        isNull,
        reason: 'sin sello la pantalla no muestra la nota',
      );

      await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 0, ahora: manana);

      expect(
        await db.arranqueDelDia(
            orgId: orgA, profileId: perfilA, ahora: manana),
        0,
      );
    });

    test('un conteo negativo no se guarda como negativo', () async {
      final int sello = await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: -3, ahora: manana);

      expect(sello, 0);
    });
  });

  group('de quién es el sello', () {
    test('dos técnicos del mismo teléfono no se pisan', () async {
      await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 7, ahora: manana);

      final int otro = await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilB, trabajoDelDia: 2, ahora: manana);

      expect(otro, 2, reason: 'el sello es del par (empresa, persona)');
      expect(
        await db.arranqueDelDia(
            orgId: orgA, profileId: perfilA, ahora: manana),
        7,
      );
    });

    test('dos empresas tampoco', () async {
      await db.sellarArranqueDelDia(
          orgId: orgA, profileId: perfilA, trabajoDelDia: 7, ahora: manana);

      final int otra = await db.sellarArranqueDelDia(
          orgId: orgB, profileId: perfilA, trabajoDelDia: 1, ahora: manana);

      expect(otra, 1);
      expect(
        await db.arranqueDelDia(
            orgId: orgB, profileId: perfilA, ahora: manana),
        1,
      );
    });
  });

  group('el día es el del teléfono', () {
    test('a las 23:59 y a las 00:01 son días distintos', () async {
      final DateTime casiMedianoche = DateTime(2026, 11, 11, 23, 59);
      final DateTime pasadaMedianoche = DateTime(2026, 11, 12, 0, 1);

      await db.sellarArranqueDelDia(
          orgId: orgA,
          profileId: perfilA,
          trabajoDelDia: 8,
          ahora: casiMedianoche);
      final int despues = await db.sellarArranqueDelDia(
          orgId: orgA,
          profileId: perfilA,
          trabajoDelDia: 1,
          ahora: pasadaMedianoche);

      expect(despues, 1,
          reason: 'una jornada nueva no hereda el denominador de la anterior');
    });
  });
}
