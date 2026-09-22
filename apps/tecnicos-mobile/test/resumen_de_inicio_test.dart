import 'package:campo/features/inicio/resumen_de_inicio.dart';
import 'package:campo/features/materiales/estado_de_jornada.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

/// Lo que la pantalla de inicio decide.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Dos cosas que se equivocan distinto.
///
/// **Cuál es el próximo trabajo** es una regla de operación: equivocarse manda
/// a una persona a la otra punta de la ciudad, y peor, deja un trabajo
/// empezado a medias para no volver.
///
/// **Qué se muestra como problema** decide dónde mira alguien a las siete de
/// la mañana. Marcar en rojo algo que se resuelve solo —una cola esperando
/// señal— enseña a ignorar los rojos, y el día que aparezca uno de verdad
/// nadie lo va a mirar.
void main() {
  TrabajoVista trabajo({
    required String id,
    int numero = 4832,
    String estado = 'asignada',
    String prioridad = '',
    String? slaVenceEn,
  }) =>
      TrabajoVista.desdeOrden(<String, dynamic>{
        'id': id,
        'numero': numero,
        'estado': estado,
        'cliente_nombre': 'Cliente $numero',
        'direccion': 'Calle 1',
        'telefono': '',
        'tipo_nombre': 'Instalación FTTH',
        'tipo_codigo': 'ftth',
        'schema_version': 1,
        'revision': 1,
        'prioridad': prioridad,
        'sla_vence_en': ?slaVenceEn,
      });

  final ahora = DateTime(2026, 9, 22, 10, 0);

  EstadoDeJornada jornada({
    int diferencias = 0,
    List<String> motivos = const <String>[],
    bool cerrada = false,
    bool hay = true,
  }) =>
      EstadoDeJornada(
        recibido: '24',
        consumido: '14',
        aDevolver: '10',
        devuelto: '10',
        diferencias: diferencias,
        ordenesAsignadas: 8,
        ordenesCompletadas: 7,
        materiales: const <MaterialDeJornada>[],
        transferencias: const <TransferenciaPendiente>[],
        motivos: motivos,
        sinSubir: 0,
        cerrada: cerrada,
        hayJornada: hay,
      );

  group('1. ¿Qué tengo hoy?', () {
    test('Cuenta los trabajos y los que ya están hechos', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'a', estado: 'cerrada'),
          trabajo(id: 'b', estado: 'completada_campo'),
          trabajo(id: 'c'),
        ],
        ahora: ahora,
      );

      expect(resumen.totalDeTrabajos, 3);
      expect(resumen.completados, 2);
      expect(resumen.pendientes, 1);
    });

    test('Un trabajo terminado y sin subir YA cuenta como hecho', () {
      // Decirle pendiente le diría al técnico que todavía tiene que ir, y ya
      // fue: lo que falta es que suba, no que lo haga.
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a', estado: 'completada_pendiente_sync')],
        ahora: ahora,
      );

      expect(resumen.completados, 1);
      expect(resumen.pendientes, 0);
    });

    test('Una devuelta para corregir sigue siendo trabajo del día', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a', estado: 'correccion_requerida')],
        ahora: ahora,
      );

      expect(resumen.completados, 0);
      expect(resumen.siguiente?.id, 'a');
    });

    test('El kit sale de la jornada, y sin jornada no se inventa', () {
      final conKit = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[], jornada: jornada(), ahora: ahora,
      );
      final sinKit = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[], ahora: ahora,
      );

      expect(conKit.hayKit, isTrue);
      expect(conKit.kitConsumido, '14');
      expect(sinKit.hayKit, isFalse);
    });
  });

  group('2. ¿Qué hago ahora?', () {
    test('El que ya está empezado gana sobre todo lo demás', () {
      // Dejar uno a medias para ir a otro es lo que hace que ninguno cierre.
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'urgente', prioridad: 'alta'),
          trabajo(id: 'empezado', estado: 'en_sitio'),
        ],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'empezado');
    });

    test('Después, el que ya va en camino', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'urgente', prioridad: 'alta'),
          trabajo(id: 'viajando', estado: 'en_camino'),
        ],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'viajando');
    });

    test('Después, el que vence antes', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'tarde', slaVenceEn: '2026-09-22T16:00:00'),
          trabajo(id: 'pronto', slaVenceEn: '2026-09-22T11:00:00'),
        ],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'pronto');
    });

    test('Un compromiso ya vencido va primero que uno que todavía no', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'a_tiempo', slaVenceEn: '2026-09-22T11:00:00'),
          trabajo(id: 'vencido', slaVenceEn: '2026-09-22T09:00:00'),
        ],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'vencido');
    });

    test('La hora prometida le gana a la prioridad de la oficina', () {
      // Una es una hora dicha a alguien que espera; la otra es una intención
      // escrita antes de saber cómo iba a ir el día.
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'marcado_alta', prioridad: 'alta'),
          trabajo(id: 'con_hora', slaVenceEn: '2026-09-22T11:00:00'),
        ],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'con_hora');
    });

    test('Sin hora, manda la prioridad', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[
          trabajo(id: 'baja', prioridad: 'baja'),
          trabajo(id: 'alta', prioridad: 'alta'),
        ],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'alta');
    });

    test('Sin ninguna señal, el primero que mandó el servidor', () {
      // No se inventa un criterio propio para desempatar: la lista ya llega
      // ordenada por quien sabe.
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'primero'), trabajo(id: 'segundo')],
        ahora: ahora,
      );

      expect(resumen.siguiente?.id, 'primero');
    });

    test('Con todo hecho no hay siguiente, y se sabe', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a', estado: 'cerrada')],
        ahora: ahora,
      );

      expect(resumen.siguiente, isNull);
      expect(resumen.terminoLaJornada, isTrue);
    });

    test('Sin trabajos, la jornada no está "terminada"', () {
      // Es distinto no tener nada asignado que haber terminado lo que había.
      final resumen = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[], ahora: ahora,
      );

      expect(resumen.terminoLaJornada, isFalse);
      expect(resumen.siguiente, isNull);
    });
  });

  group('3. ¿Tengo problemas?', () {
    test('Sin nada roto, no hay avisos', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a')],
        jornada: jornada(),
        ahora: ahora,
      );

      expect(resumen.hayProblemas, isFalse);
      expect(resumen.avisos, isEmpty);
    });

    test('Lo que espera señal se avisa, pero no como alarma', () {
      // Sube solo. Marcarlo en rojo enseñaría a ignorar los rojos.
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a')],
        movimientosSinSubir: 2,
        evidenciasSinSubir: 1,
        ahora: ahora,
      );

      expect(resumen.avisos, hasLength(1));
      expect(resumen.avisos.single.gravedad, GravedadDeAviso.media);
      expect(resumen.avisos.single.titulo, contains('3'));
    });

    test('Un cambio rechazado sí es grave: no se arregla solo', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a')],
        mutacionesEnConflicto: 1,
        ahora: ahora,
      );

      expect(resumen.avisos.single.gravedad, GravedadDeAviso.alta);
    });

    test('Un material que no cuadra se avisa antes de cerrar', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornada(diferencias: 2),
        ahora: ahora,
      );

      expect(resumen.avisos.single.titulo, contains('2 materiales'));
      expect(resumen.avisos.single.gravedad, GravedadDeAviso.alta);
    });

    test('Un equipo sin ubicar se muestra con el motivo del servidor', () {
      // Lo escribió quien sabe por qué no cuadra: reescribirlo sería adivinar.
      final resumen = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornada(motivos: <String>[
          'El equipo con serie 48575448A9B0C1 no se instaló ni volvió a bodega.',
        ]),
        ahora: ahora,
      );

      expect(resumen.avisos.single.titulo, 'Un equipo sin ubicar');
      expect(resumen.avisos.single.detalle, contains('48575448A9B0C1'));
    });

    test('Lo grave se muestra antes que lo que puede esperar', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornada(diferencias: 1),
        movimientosSinSubir: 5,
        ahora: ahora,
      );

      expect(resumen.avisos.first.gravedad, GravedadDeAviso.alta);
      expect(resumen.avisos.last.gravedad, GravedadDeAviso.media);
    });

    test('Una jornada ya cerrada no sigue reclamando', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: const <TrabajoVista>[],
        jornada: jornada(diferencias: 3, cerrada: true),
        ahora: ahora,
      );

      expect(resumen.avisos, isEmpty);
      expect(resumen.jornadaCerrada, isTrue);
    });

    test('Sin jornada cargada tampoco se inventan problemas', () {
      final resumen = ResumenDeInicio.armar(
        trabajos: <TrabajoVista>[trabajo(id: 'a')],
        jornada: jornada(hay: false, diferencias: 9),
        ahora: ahora,
      );

      expect(resumen.avisos, isEmpty);
    });
  });
}
