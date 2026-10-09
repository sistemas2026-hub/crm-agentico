import 'dart:async';
import 'dart:io';

import 'package:campo/core/estado/ordenes_jornada.dart';
import 'package:campo/core/sync/sync_queue_service.dart';
import 'package:campo/core/theme/app_theme.dart';
import 'package:campo/features/detalle_orden/acciones_orden.dart';
import 'package:campo/features/detalle_orden/detalle_orden_screen.dart';
import 'package:campo/features/inicio/inicio_screen.dart';
import 'package:campo/features/materiales/devolucion_screen.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/materiales/kit_de_jornada.dart';
import 'package:campo/features/materiales/material_en_custodia.dart';
import 'package:campo/features/materiales/materiales_screen.dart';
import 'package:campo/features/trabajo/trabajo_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;

import 'apoyo/estado_visual.dart';

/// Dos imágenes idénticas, byte a byte.
bool _mismosBytes(List<int> a, List<int> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

/// La matriz de estados: cada situación real, con lo que se espera de ella.
///
/// QUÉ CUBRE Y QUÉ NO
/// ------------------
/// Sólo estados **operativos**: los que le pueden pasar a alguien un martes.
/// No se combinan por combinar —"vacío y en conflicto a la vez" no existe— y
/// no se inventan situaciones para llenar una tabla.
///
/// Lo que se afirma de cada uno es lo mismo: qué aparece, qué **no** aparece,
/// qué puede tocar la persona, y si puede seguir. El "qué no aparece" es el
/// que más atrapa: casi siempre es el texto de otro estado, y así se descubre
/// que dos situaciones distintas dicen lo mismo.
///
/// DÓNDE VIVEN LOS ESTADOS DE RED
/// ------------------------------
/// `InicioScreen`, el detalle y la jornada reciben el estado de la cola y lo
/// muestran. `TrabajoScreen` y `MaterialesScreen` **no**: en esas pantallas la
/// señal se ve en la franja del armazón, que está arriba de todas. Es una
/// decisión, no un hueco — repetir "sin conexión" en cada pantalla es ruido
/// cuando ya está fijo en el encabezado. Por eso sus estados de red se montan
/// con el armazón y no con la pantalla suelta.
void main() {
  final DateTime ahora = DateTime(2026, 9, 22, 10, 0);

  // --- Insumos compartidos -------------------------------------------------

  Map<String, dynamic> orden({
    String id = 'ot-1',
    int numero = 4832,
    String estado = 'en_sitio',
    String cliente = 'Carlos Gómez Rincón',
  }) =>
      <String, dynamic>{
        'id': id,
        'numero': numero,
        'estado': estado,
        'cliente_nombre': cliente,
        'direccion': 'Cra 45 #12-88',
        'telefono': '3001234567',
        'tipo_nombre': 'Instalación FTTH',
        'tipo_codigo': 'ftth_instalacion',
        'schema_version': 1,
        'revision': 7,
        'diagnostico_previo_ia': '',
        'resumen': 'Diagnóstico en domicilio',
      };

  SyncSummary sync({
    bool sinConexion = false,
    bool enviando = false,
    int pendientes = 0,
    int conflicto = 0,
  }) =>
      SyncSummary(
        status: enviando
            ? SyncStatus.syncing
            : (conflicto > 0 ? SyncStatus.error : SyncStatus.idle),
        isSyncing: enviando,
        hasConnectionError: sinConexion,
        mutacionesPendientes: pendientes,
        mutacionesConflicto: conflicto,
        evidenciasPendientes: 0,
        datosDirty: 0,
      );

  /// Las órdenes compartidas. `falla` simula que la base no se pudo leer.
  final List<OrdenesJornada> vivas = <OrdenesJornada>[];
  final List<StreamController<SyncStatus>> canales =
      <StreamController<SyncStatus>>[];

  OrdenesJornada listaDe(
    List<Map<String, dynamic>> filas, {
    bool falla = false,
  }) {
    final StreamController<SyncStatus> avisos =
        StreamController<SyncStatus>.broadcast();
    canales.add(avisos);
    final OrdenesJornada o = OrdenesJornada(
      leerOrdenes: () async {
        if (falla) throw StateError('base ilegible');
        return filas;
      },
      sincronizar: () async {},
      avisosDeSincronizacion: avisos.stream,
    );
    vivas.add(o);
    return o;
  }

  tearDownAll(() async {
    for (final StreamController<SyncStatus> c in canales) {
      await c.close();
    }
    for (final OrdenesJornada o in vivas) {
      o.dispose();
    }
  });

  EstadoDeJornada jornada({
    bool hay = true,
    int diferencias = 0,
    List<String> motivos = const <String>[],
    bool cerrada = false,
    bool cierreTomado = false,
    int sinSubir = 0,
    List<MaterialDeJornada> materiales = const <MaterialDeJornada>[],
  }) =>
      EstadoDeJornada(
        recibido: '24',
        consumido: '14',
        aDevolver: '10',
        devuelto: '10',
        diferencias: diferencias,
        ordenesAsignadas: 4,
        ordenesCompletadas: 3,
        materiales: materiales,
        transferencias: const <TransferenciaPendiente>[],
        motivos: motivos,
        sinSubir: sinSubir,
        cerrada: cerrada,
        hayJornada: hay,
        cierreTomado: cierreTomado,
      );

  const MaterialDeJornada conector = MaterialDeJornada(
    codigo: 'CON-SC-APC',
    nombre: 'Conector SC/APC',
    unidad: 'unidades',
    esperado: '7',
    devuelto: '7',
    diferencia: 0,
    porDevolver: 0,
  );

  const MaterialEnCustodia unConector = MaterialEnCustodia(
    categoria: 'Consumibles',
    nombre: 'Conector SC/APC',
    detalle: 'Reconectorización',
    clase: ClaseMaterial.consumible,
    recibidos: 10,
    usados: 3,
    unidad: 'unidades',
  );

  Widget enApp(Widget pantalla) => MaterialApp(
        theme: AppTheme.lightTheme,
        home: pantalla is Scaffold ? pantalla : Scaffold(body: pantalla),
      );

  void pantallaAlta(WidgetTester tester) {
    tester.view.physicalSize = const Size(1000, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  /// Recorre una matriz: monta cada estado y le exige lo suyo.
  void correr(String pantalla, List<EstadoVisual> estados) {
    group(pantalla, () {
      for (final EstadoVisual estado in estados) {
        testWidgets('${estado.nombre} — ${estado.porQue}',
            (WidgetTester t) async {
          pantallaAlta(t);
          await t.pumpWidget(enApp(estado.montar()));
          await t.pumpAndSettle();
          estado.verificar(t);
        });
      }
    });
  }

  // --- HOME ----------------------------------------------------------------

  InicioScreen inicio({
    List<Map<String, dynamic>> filas = const <Map<String, dynamic>>[],
    bool falla = false,
    SyncSummary? resumen,
    EstadoDeJornada? dia,
  }) =>
      InicioScreen(
        ordenes: listaDe(filas, falla: falla),
        nombreTecnico: 'Carlos Gómez',
        resumenSincronizacion: resumen,
        jornada: dia ?? jornada(hay: false),
        ahora: ahora,
        abrirTrabajo: (_, _) async {},
      );

  correr('HOME', <EstadoVisual>[
    EstadoVisual(
      nombre: 'normal',
      porQue: 'hay trabajo y nada roto',
      montar: () => inicio(
        filas: <Map<String, dynamic>>[orden()],
        resumen: sync(),
        dia: jornada(),
      ),
      apareceTexto: <String>['Próximo trabajo', 'Jornada en curso'],
      apareceParcial: <String>['Diagnóstico en domicilio'],
      noAparece: <String>[
        'No tenés trabajos asignados',
        'No se pudieron leer',
        'Alertas operativas',
      ],
      accionDisponible: 'CONTINUAR OT #4832',
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'sin_trabajos',
      porQue: 'el despacho no asignó nada',
      montar: () => inicio(resumen: sync()),
      apareceTexto: <String>['No tenés trabajos asignados'],
      noAparece: <String>[
        'Terminaste todos tus trabajos',
        'Próximo trabajo',
        'No se pudieron leer',
      ],
      accionAusente: 'CONTINUAR OT #4832',
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'offline',
      porQue: 'sin señal, pero se sigue trabajando',
      montar: () => inicio(
        filas: <Map<String, dynamic>>[orden()],
        resumen: sync(sinConexion: true, pendientes: 2),
      ),
      apareceParcial: <String>['se envían al volver la conexión'],
      noAparece: <String>['Todo sincronizado', 'Enviando cambios'],
      accionDisponible: 'CONTINUAR OT #4832',
      // Lo importante del estado offline: NO frena el trabajo.
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'sincronizando',
      porQue: 'la cola está enviando ahora',
      montar: () => inicio(
        filas: <Map<String, dynamic>>[orden()],
        resumen: sync(enviando: true, pendientes: 2),
      ),
      apareceParcial: <String>['Enviando cambios al servidor'],
      noAparece: <String>[
        'se envían al volver la conexión',
        'Todo sincronizado',
      ],
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'error',
      porQue: 'la base local no se pudo leer',
      montar: () => inicio(falla: true, resumen: sync()),
      apareceTexto: <String>['No se pudieron leer tus trabajos'],
      noAparece: <String>[
        'No tenés trabajos asignados',
        'Próximo trabajo',
      ],
      permiteContinuar: false,
    ),
  ]);

  // --- TRABAJO -------------------------------------------------------------

  TrabajoScreen trabajo({
    List<Map<String, dynamic>> filas = const <Map<String, dynamic>>[],
    bool falla = false,
  }) =>
      TrabajoScreen(
        ordenes: listaDe(filas, falla: falla),
        abrirTrabajo: (_, _) async {},
      );

  correr('TRABAJO', <EstadoVisual>[
    EstadoVisual(
      nombre: 'normal',
      porQue: 'la lista tiene trabajos',
      montar: () => trabajo(filas: <Map<String, dynamic>>[orden()]),
      apareceParcial: <String>['Carlos Gómez'],
      noAparece: <String>['No se pudieron leer tus trabajos'],
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'vacio',
      porQue: 'no hay nada en esta pestaña',
      montar: trabajo,
      noAparece: <String>['No se pudieron leer tus trabajos'],
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'error',
      porQue: 'la base local no se pudo leer',
      montar: () => trabajo(falla: true),
      apareceTexto: <String>['No se pudieron leer tus trabajos'],
      apareceParcial: <String>['Deslizá hacia abajo'],
      permiteContinuar: false,
    ),
  ]);

  // --- DETALLE DE OT -------------------------------------------------------

  DetalleOrdenScreen detalle({
    List<Map<String, dynamic>>? filas,
    String id = 'ot-1',
    SyncSummary? resumen,
  }) =>
      DetalleOrdenScreen(
        ordenId: id,
        ordenes: listaDe(filas ?? <Map<String, dynamic>>[orden()]),
        acciones: AccionesOrden(
          transicionar: ({
            required String ordenId,
            required String nuevoEstadoLocal,
            required String tipoAccion,
            required int revisionBase,
          }) async {},
          sincronizar: () async {},
        ),
        resumenInicial: resumen,
      );

  correr('DETALLE OT', <EstadoVisual>[
    EstadoVisual(
      nombre: 'normal',
      porQue: 'la orden está en curso',
      montar: () => detalle(resumen: sync()),
      apareceTexto: <String>['OT #4832'],
      apareceParcial: <String>['Carlos Gómez'],
      noAparece: <String>['No encontramos esta orden'],
      accionDisponible: 'Ejecutar el trabajo',
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'vacio',
      porQue: 'la orden ya no está: la reasignaron',
      montar: () => detalle(id: 'ot-que-no-existe', resumen: sync()),
      apareceTexto: <String>['No encontramos esta orden'],
      apareceParcial: <String>['Puede haber sido reasignada'],
      noAparece: <String>['Ejecutar el trabajo'],
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'offline',
      porQue: 'sin señal; el trabajo sigue',
      montar: () => detalle(resumen: sync(sinConexion: true, pendientes: 1)),
      apareceTexto: <String>['OT #4832'],
      accionDisponible: 'Ejecutar el trabajo',
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'sincronizando',
      porQue: 'la cola está enviando',
      montar: () => detalle(resumen: sync(enviando: true, pendientes: 1)),
      apareceTexto: <String>['OT #4832'],
      accionDisponible: 'Ejecutar el trabajo',
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'conflicto',
      porQue: 'el servidor rechazó un cambio',
      montar: () => detalle(resumen: sync(conflicto: 1)),
      apareceTexto: <String>['OT #4832'],
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'completo',
      porQue: 'el trabajo se terminó y espera turno para subir',
      montar: () => detalle(
        filas: <Map<String, dynamic>>[
          orden(estado: 'completada_pendiente_sync'),
        ],
        resumen: sync(pendientes: 1),
      ),
      apareceTexto: <String>['OT #4832'],
      noAparece: <String>['No encontramos esta orden'],
      // Ya no se ejecuta: está hecho.
      accionAusente: 'Ejecutar el trabajo',
      permiteContinuar: false,
    ),
  ]);

  // --- MATERIALES ----------------------------------------------------------

  /// La matriz mide la conducta del PRODUCTO, no la de la demostración.
  ///
  /// Con la bandera encendida, un kit vacío se rellena con el catálogo de
  /// ejemplo, y entonces "sin kit" deja de existir como estado. Se fija en
  /// falso para que la matriz diga lo mismo en las dos compilaciones.
  MaterialesScreen materiales({KitDeJornada? kit}) => MaterialesScreen(
        tecnico: 'Carlos Gómez',
        mostrarDatosFuturos: false,
        kit: kit ?? const KitDeJornada.vacio(),
      );

  correr('MATERIALES', <EstadoVisual>[
    EstadoVisual(
      nombre: 'normal',
      porQue: 'hay kit entregado y todo cuadra',
      montar: () => materiales(
        kit: const KitDeJornada(
          materiales: <MaterialEnCustodia>[unConector],
          acta: 'Acta #K-2026-311',
          sinSubir: 0,
          conNovedad: <MovimientoConNovedad>[],
        ),
      ),
      apareceTexto: <String>['Mi Kit', 'Acta #K-2026-311'],
      noAparece: <String>['Todavía no hay material entregado'],
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'sin_kit',
      porQue: 'la bodega todavía no entregó nada',
      montar: materiales,
      apareceParcial: <String>['Todavía no hay material entregado'],
      noAparece: <String>['Mi Kit Diario', 'Acta #'],
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'con_pendientes',
      porQue: 'hay movimientos esperando señal',
      montar: () => materiales(
        kit: const KitDeJornada(
          materiales: <MaterialEnCustodia>[unConector],
          acta: 'Acta #K-2026-311',
          sinSubir: 3,
          conNovedad: <MovimientoConNovedad>[],
        ),
      ),
      apareceTexto: <String>['Mi Kit'],
      permiteContinuar: true,
    ),
  ]);

  // --- JORNADA -------------------------------------------------------------

  DevolucionScreen cierre({EstadoDeJornada? estado}) =>
      DevolucionScreen(estado: estado ?? jornada());

  correr('JORNADA', <EstadoVisual>[
    EstadoVisual(
      nombre: 'normal',
      porQue: 'todo devuelto y sin diferencias',
      montar: () => cierre(
        estado: jornada(materiales: const <MaterialDeJornada>[conector]),
      ),
      apareceTexto: <String>['Cierre de jornada', 'Kit de hoy'],
      apareceParcial: <String>['Correcto'],
      noAparece: <String>[
        'Todavía no hay una jornada que cerrar',
        'Falta resolver esto',
      ],
      accionDisponible: 'Cerrar jornada',
      permiteContinuar: true,
    ),
    EstadoVisual(
      nombre: 'sin_jornada',
      porQue: 'no hay kit a nombre de nadie todavía',
      montar: () => cierre(estado: jornada(hay: false)),
      apareceParcial: <String>['Todavía no hay una jornada que cerrar'],
      noAparece: <String>['Kit de hoy', 'Material a devolver'],
      accionAusente: 'Cerrar jornada',
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'diferencia_bloqueante',
      porQue: 'falta material sin explicar: no se puede cerrar',
      montar: () => cierre(
        estado: jornada(
          diferencias: 1,
          materiales: const <MaterialDeJornada>[conector],
          motivos: <String>['Conector SC/APC: faltan 2 unidades sin explicar.'],
        ),
      ),
      apareceParcial: <String>[
        'Falta resolver esto',
        'faltan 2 unidades sin explicar',
      ],
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'cierre_pendiente_sync',
      porQue: 'el técnico ya cerró; el servidor todavía no confirmó',
      montar: () => cierre(
        estado: jornada(
          cierreTomado: true,
          materiales: const <MaterialDeJornada>[conector],
        ),
      ),
      apareceParcial: <String>['Kit de hoy'],
      // Lo que NO puede decir: que la jornada está cerrada. Todavía no lo
      // está, y creer que sí es irse a casa con el trabajo sin entregar.
      noAparece: <String>['Jornada cerrada'],
      permiteContinuar: false,
    ),
    EstadoVisual(
      nombre: 'cerrada',
      porQue: 'el servidor confirmó y congeló el acta',
      montar: () => cierre(
        estado: jornada(
          cerrada: true,
          materiales: const <MaterialDeJornada>[conector],
        ),
      ),
      apareceParcial: <String>['Kit de hoy'],
      accionAusente: 'Cerrar jornada',
      permiteContinuar: false,
    ),
  ]);

  // --- Estados que no pueden confundirse ------------------------------------

  group('Dos estados distintos no se dibujan igual', () {
    /// Los grupos que tienen que distinguirse dentro de una misma pantalla.
    ///
    /// No se comparan estados de pantallas distintas: que el vacío de Trabajo
    /// se parezca al de Materiales no confunde a nadie, porque no se ven uno
    /// al lado del otro.
    const Map<String, List<String>> familias = <String, List<String>>{
      'detalle': <String>[
        'matriz_detalle_normal',
        'matriz_detalle_offline',
        'matriz_detalle_sincronizando',
        'matriz_detalle_conflicto',
      ],
      'jornada': <String>[
        'matriz_jornada_normal',
        'matriz_jornada_cierre_tomado',
        'matriz_jornada_cerrada',
      ],
      'materiales': <String>[
        'matriz_materiales_normal',
        'matriz_materiales_pendientes',
        'matriz_materiales_novedad',
        // Una diferencia de cantidad y un conflicto de identidad se
        // resuelven distinto: uno lo explica el tecnico, el otro lo
        // destraba el supervisor. Antes los dos eran "Novedades: 1".
        'matriz_materiales_conflicto_serial',
      ],
    };

    /// Los pares que SÍ pueden verse iguales, con el motivo.
    ///
    /// Ninguno por ahora. Cuando aparezca uno legítimo se anota acá con su
    /// razón, y así queda a la vista en vez de disolverse en un "ya lo
    /// sabíamos".
    const Set<String> paresAceptados = <String>{};

    List<int> bytesDe(String nombre) {
      final File f = File(
        p.join(Directory.current.path, 'test', 'capturas',
            '${nombre}_390x2600.png'),
      );
      if (!f.existsSync()) {
        fail('Falta la captura de $nombre. Generalas con:\n'
            '  flutter test test/capturas_qa_test.dart --run-skipped '
            '--update-goldens');
      }
      return f.readAsBytesSync();
    }

    for (final MapEntry<String, List<String>> familia in familias.entries) {
      test('En ${familia.key}, cada estado se ve distinto', () {
        final List<String> iguales = <String>[];

        for (var i = 0; i < familia.value.length; i++) {
          for (var j = i + 1; j < familia.value.length; j++) {
            final String a = familia.value[i];
            final String b = familia.value[j];
            if (paresAceptados.contains('$a|$b')) continue;

            final List<int> unos = bytesDe(a);
            final List<int> otros = bytesDe(b);
            if (_mismosBytes(unos, otros)) iguales.add('$a == $b');
          }
        }

        expect(
          iguales,
          isEmpty,
          reason: 'estos estados significan cosas distintas y se dibujan '
              'exactamente igual, asi que el tecnico no puede saber en cual '
              'esta:\n${iguales.join('\n')}',
        );
      });
    }
  });

}
