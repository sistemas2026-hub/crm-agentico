import 'package:campo/core/storage/local_database.dart';
import 'package:campo/core/storage/secure_storage_service.dart';
import 'package:campo/features/ejecucion/datos_de_ejecucion.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'apoyo/fuente_de_ejecucion_falsa.dart';

/// La fuente real, contra la base de verdad.
///
/// PARA QUÉ ESTA PRUEBA
/// --------------------
/// Separar la pantalla de la base sirve para poder dibujarla con un fixture.
/// Pero un fixture sólo vale si entrega lo mismo que la base: si devolviera
/// los datos "más lindos" —claves en camelCase, JSON ya decodificado— las
/// pruebas pasarían contra una forma que en el teléfono no existe nunca, y la
/// pantalla se rompería justo en producción.
///
/// Acá se carga una orden real desde SQLite con `FuenteLocalDeEjecucion` y se
/// comprueba que lo que sale tiene la misma forma que el fixture y que las
/// reglas derivadas dan el mismo resultado.
///
/// Sin widgets a propósito: mezclar FFI con pruebas de widget en un mismo
/// archivo ya colgó la suite de este proyecto una vez.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  LocalDatabase.usarBaseDePruebas('pruebas_fuente_ejecucion.db');

  const String org = 'org_rapilink';
  const String perfil = 'prof_carlos';

  late LocalDatabase db;

  setUpAll(() async {
    LocalDatabase.resetForTesting();
    await databaseFactory.deleteDatabase(
      join(await databaseFactory.getDatabasesPath(),
          'pruebas_fuente_ejecucion.db'),
    );
  });

  setUp(() async {
    db = LocalDatabase();
    final base = await db.database;
    await base.delete('local_ordenes');
  });

  /// Una orden con la misma plantilla que usa el fixture.
  Future<void> sembrar() async {
    await db.upsertOrden(
      orgId: org,
      profileId: perfil,
      ordenData: <String, dynamic>{
        'id': 'ot-1',
        'numero': 4832,
        'estado': 'en_sitio',
        'cliente_nombre': 'Carlos Gómez Rincón',
        'direccion': 'Cra 45 #12-88, Barrio San José',
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
  }

  FuenteLocalDeEjecucion fuenteReal() => FuenteLocalDeEjecucion(
        baseLocal: db,
        almacenamiento: _SesionFija(org, perfil),
      );

  group('1. La fuente real entrega lo que la pantalla espera', () {
    test('Carga la orden con su plantilla', () async {
      await sembrar();

      final DatosDeEjecucion? datos = await fuenteReal().cargar('ot-1');

      expect(datos, isNotNull);
      expect(datos!.orgId, org);
      expect(datos.profileId, perfil);
      expect(datos.numeroDeOrden, 4832);
      expect(datos.revision, 7);
      expect(datos.campos, hasLength(4));
      expect(datos.requisitosDeEvidencia, hasLength(3));
    });

    test('Sin identidad no devuelve nada, en vez de una orden vacía', () async {
      await sembrar();

      final DatosDeEjecucion? datos = await FuenteLocalDeEjecucion(
        baseLocal: db,
        almacenamiento: _SesionFija(null, null),
      ).cargar('ot-1');

      expect(datos, isNull);
    });

    test('Con la orden ausente tampoco', () async {
      expect(await fuenteReal().cargar('ot-inexistente'), isNull);
    });

    test('Y no cruza la orden de otra persona', () async {
      await sembrar();

      final DatosDeEjecucion? ajena = await FuenteLocalDeEjecucion(
        baseLocal: db,
        almacenamiento: _SesionFija(org, 'prof_pedro'),
      ).cargar('ot-1');

      expect(ajena, isNull, reason: 'la orden es de otro perfil');
    });
  });

  group('2. La base y el fixture dan el mismo resultado', () {
    test('Las mismas reglas, sobre los mismos datos', () async {
      // Lo que de verdad se compara: que las decisiones que toma la pantalla
      // no cambien según de dónde vinieron los datos.
      await sembrar();

      final DatosDeEjecucion real = (await fuenteReal().cargar('ot-1'))!;
      final DatosDeEjecucion falso =
          (await FuenteDeEjecucionFalsa().cargar('ot-1'))!;

      expect(real.camposObligatoriosSinLlenar,
          falso.camposObligatoriosSinLlenar);
      expect(real.exigeFirma, falso.exigeFirma);
      expect(real.hayFirma, falso.hayFirma);
      expect(real.firmaSinSubir, falso.firmaSinSubir);
      expect(real.cierre.puedeCerrar, falso.cierre.puedeCerrar);
      expect(real.numeroDeOrden, falso.numeroDeOrden);
      expect(real.revision, falso.revision);
    });

    test('Las claves de la fila son las de la base, no versiones amables',
        () async {
      // Si el fixture usara camelCase o JSON ya decodificado, la pantalla se
      // probaría contra algo que en el teléfono no pasa nunca.
      await sembrar();

      final DatosDeEjecucion real = (await fuenteReal().cargar('ot-1'))!;
      final DatosDeEjecucion falso =
          (await FuenteDeEjecucionFalsa().cargar('ot-1'))!;

      for (final String clave in <String>[
        'id',
        'numero',
        'revision',
        'estado',
        'cliente_nombre',
        'formulario_campos_json',
        'formulario_evidencias_json',
      ]) {
        expect(real.orden.containsKey(clave), isTrue,
            reason: 'la base trae $clave');
        expect(falso.orden.containsKey(clave), isTrue,
            reason: 'el fixture tiene que traer $clave igual');
      }

      expect(real.orden['formulario_campos_json'], isA<String>(),
          reason: 'en la base es texto JSON');
      expect(falso.orden['formulario_campos_json'], isA<String>(),
          reason: 'y en el fixture también');
    });
  });

  group('3. Lo que se escribe llega a la base', () {
    test('Un campo guardado se lee de vuelta en la siguiente carga', () async {
      await sembrar();
      final FuenteLocalDeEjecucion fuente = fuenteReal();

      await fuente.guardarCampo(
        orgId: org,
        profileId: perfil,
        ordenId: 'ot-1',
        clave: 'potencia_rx',
        valor: '-18.4',
      );

      final DatosDeEjecucion datos = (await fuente.cargar('ot-1'))!;
      expect(datos.valores['potencia_rx'], '-18.4');
      expect(
        datos.camposObligatoriosSinLlenar,
        isNot(contains('Potencia óptica en roseta (dBm)')),
        reason: 'ese campo ya está respondido',
      );
    });
  });
}

/// Una sesión que devuelve siempre lo mismo, sin tocar el almacenamiento
/// seguro del sistema.
class _SesionFija implements SecureStorageLectura {
  _SesionFija(this._org, this._perfil);

  final String? _org;
  final String? _perfil;

  @override
  Future<String?> getOrgId() async => _org;

  @override
  Future<String?> getProfileId() async => _perfil;
}
