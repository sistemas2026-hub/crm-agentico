import 'package:campo/features/ejecucion/cierre_de_orden.dart';
import 'package:flutter_test/flutter_test.dart';

/// Qué deja cerrar un trabajo y qué no.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Dos errores opuestos, y los dos caros.
///
/// Dejar cerrar sin lo obligatorio manda al técnico a la casa siguiente con un
/// trabajo que el servidor va a rechazar; cuando eso se descubre, ya está a
/// veinte cuadras y el cliente cerró la puerta.
///
/// Bloquear por lo que no corresponde —una foto opcional, un material que
/// nadie gastó, una cola que todavía no subió— deja a la cuadrilla parada en
/// una vereda esperando señal. Y lo que hace es enseñarle a la gente a evitar
/// la aplicación.
///
/// La frontera la decide Dexter con `obligatorio`, no el teléfono.
void main() {
  List<Map<String, dynamic>> foto(String id, {bool obligatorio = true}) =>
      <Map<String, dynamic>>[
        {'id': id, 'descripcion': 'Foto $id', 'obligatorio': obligatorio},
      ];

  CierreDeOrden evaluar({
    List<String> camposSinLlenar = const <String>[],
    List<dynamic> requisitos = const <dynamic>[],
    List<Map<String, dynamic>> fotos = const <Map<String, dynamic>>[],
    List<Map<String, dynamic>> materiales = const <Map<String, dynamic>>[],
    bool exigeFirma = false,
    bool hayFirma = false,
    bool firmaSinSubir = false,
  }) =>
      CierreDeOrden.evaluar(
        camposObligatoriosSinLlenar: camposSinLlenar,
        requisitosDeFoto: requisitos,
        fotosCapturadas: fotos,
        materialesRegistrados: materiales,
        exigeFirma: exigeFirma,
        hayFirma: hayFirma,
        firmaSinSubir: firmaSinSubir,
      );

  group('1. Un trabajo sin nada pendiente se puede cerrar', () {
    test('Sin fotos pedidas y sin material, cierra', () {
      final cierre = evaluar();

      expect(cierre.puedeCerrar, isTrue);
      expect(cierre.bloqueantes, isEmpty);
    });

    test('El checklist tiene siempre las mismas líneas', () {
      // Un checklist que aparece y desaparece obliga a leerlo entero cada vez.
      final vacio = evaluar();
      final lleno = evaluar(
        requisitos: foto('a'),
        fotos: <Map<String, dynamic>>[{'requisito_id': 'a'}],
        materiales: <Map<String, dynamic>>[
          {'estado': 'confirmado', 'resultado': 'aceptado'},
        ],
      );

      expect(vacio.requisitos.map((r) => r.titulo).toList(), <String>[
        'Datos del trabajo',
        'Evidencia fotográfica',
        'Materiales utilizados',
      ]);
      expect(lleno.requisitos.map((r) => r.titulo).toList(),
          vacio.requisitos.map((r) => r.titulo).toList());
    });
  });

  group('2. Lo obligatorio lo decide Dexter', () {
    test('Un campo obligatorio sin llenar bloquea', () {
      final cierre = evaluar(camposSinLlenar: <String>['Potencia RX']);

      expect(cierre.puedeCerrar, isFalse);
      expect(cierre.bloqueantes.single.titulo, 'Datos del trabajo');
      expect(cierre.bloqueantes.single.detalle, contains('Potencia RX'));
    });

    test('Una foto obligatoria sin tomar bloquea', () {
      final cierre = evaluar(requisitos: foto('a'));

      expect(cierre.puedeCerrar, isFalse);
      expect(cierre.bloqueantes.single.titulo, 'Evidencia fotográfica');
    });

    test('Una foto OPCIONAL sin tomar no bloquea, pero se ve', () {
      final cierre = evaluar(requisitos: foto('a', obligatorio: false));

      expect(cierre.puedeCerrar, isTrue);
      final linea = cierre.requisitos
          .firstWhere((r) => r.titulo == 'Evidencia fotográfica');
      expect(linea.estado, EstadoDeRequisito.opcional);
      expect(linea.detalle, contains('opcional'));
    });

    test('Con la obligatoria tomada, la opcional que falta no bloquea', () {
      final cierre = evaluar(
        requisitos: <dynamic>[
          ...foto('a'),
          ...foto('b', obligatorio: false),
        ],
        fotos: <Map<String, dynamic>>[{'requisito_id': 'a'}],
      );

      expect(cierre.puedeCerrar, isTrue);
    });

    test('Varios campos sin llenar se cuentan, no se enumeran', () {
      final cierre = evaluar(
        camposSinLlenar: <String>['Potencia RX', 'Serial ONT', 'Puerto'],
      );

      expect(cierre.bloqueantes.single.detalle, contains('3'));
    });
  });

  group('3. Los materiales nunca bloquean', () {
    test('Una OT sin materiales cierra igual', () {
      // Hay trabajos que no gastan nada: una revisión, una medición. Exigir
      // material ahí obligaría a inventar un consumo para poder cerrar.
      final cierre = evaluar();

      final linea = cierre.requisitos
          .firstWhere((r) => r.titulo == 'Materiales utilizados');
      expect(linea.estado, EstadoDeRequisito.opcional);
      expect(cierre.puedeCerrar, isTrue);
    });

    test('Una OT con consumo confirmado lo muestra completo', () {
      final cierre = evaluar(materiales: <Map<String, dynamic>>[
        {'estado': 'confirmado', 'resultado': 'aceptado'},
        {'estado': 'confirmado', 'resultado': 'aceptado'},
      ]);

      final linea = cierre.requisitos
          .firstWhere((r) => r.titulo == 'Materiales utilizados');
      expect(linea.estado, EstadoDeRequisito.completo);
      expect(linea.detalle, contains('2'));
    });

    test('Un consumo sin subir no bloquea, pero se avisa', () {
      final cierre = evaluar(materiales: <Map<String, dynamic>>[
        {'estado': 'pendiente'},
      ]);

      final linea = cierre.requisitos
          .firstWhere((r) => r.titulo == 'Materiales utilizados');
      expect(linea.estado, EstadoDeRequisito.sinSubir);
      expect(cierre.puedeCerrar, isTrue);
      expect(cierre.hayPendienteDeSubir, isTrue);
    });

    test('Un descuadre se ve con su motivo y tampoco bloquea', () {
      final cierre = evaluar(materiales: <Map<String, dynamic>>[
        {
          'estado': 'confirmado',
          'resultado': 'descuadre',
          'motivo': 'Se registraron 30 y había 24.',
        },
      ]);

      final linea = cierre.requisitos
          .firstWhere((r) => r.titulo == 'Materiales utilizados');
      expect(linea.estado, EstadoDeRequisito.conConflicto);
      expect(linea.detalle, contains('30'));
      expect(cierre.puedeCerrar, isTrue,
          reason: 'el trabajo se hizo; el descuadre lo resuelve la oficina');
      expect(cierre.hayConflictos, isTrue);
    });

    test('Un equipo repetido también se ve', () {
      final cierre = evaluar(materiales: <Map<String, dynamic>>[
        {
          'estado': 'confirmado',
          'resultado': 'conflicto',
          'motivo': 'La serie 48575448A9B0C1 ya figura instalada.',
        },
      ]);

      expect(cierre.hayConflictos, isTrue);
      final linea = cierre.requisitos
          .firstWhere((r) => r.titulo == 'Materiales utilizados');
      expect(linea.detalle, contains('48575448A9B0C1'));
    });
  });

  group('4. La firma, solo si esta empresa la pide', () {
    test('Sin exigencia, no aparece la línea', () {
      final cierre = evaluar(exigeFirma: false);

      expect(
        cierre.requisitos.any((r) => r.titulo == 'Firma del cliente'),
        isFalse,
        reason: 'no se inventa un requisito que nadie declaró',
      );
    });

    test('Exigida y sin firmar, bloquea', () {
      final cierre = evaluar(exigeFirma: true, hayFirma: false);

      expect(cierre.puedeCerrar, isFalse);
      expect(cierre.bloqueantes.single.titulo, 'Firma del cliente');
    });

    test('Firmada, deja cerrar', () {
      final cierre = evaluar(exigeFirma: true, hayFirma: true);

      expect(cierre.puedeCerrar, isTrue);
    });

    test('Firmada sin subir tampoco bloquea: la cola sube sola', () {
      final cierre = evaluar(
        exigeFirma: true, hayFirma: true, firmaSinSubir: true,
      );

      expect(cierre.puedeCerrar, isTrue);
      expect(cierre.hayPendienteDeSubir, isTrue);
      final linea =
          cierre.requisitos.firstWhere((r) => r.titulo == 'Firma del cliente');
      expect(linea.estado, EstadoDeRequisito.sinSubir);
      expect(linea.detalle, contains('señal'));
    });
  });

  group('5. Cerrar sin señal es cerrar', () {
    test('Todo hecho y nada subido: se puede cerrar igual', () {
      // Un trabajo terminado sin señal está terminado. Bloquear acá dejaría a
      // la cuadrilla esperando red en la puerta del cliente.
      final cierre = evaluar(
        requisitos: foto('a'),
        fotos: <Map<String, dynamic>>[{'requisito_id': 'a'}],
        materiales: <Map<String, dynamic>>[{'estado': 'pendiente'}],
        exigeFirma: true,
        hayFirma: true,
        firmaSinSubir: true,
      );

      expect(cierre.puedeCerrar, isTrue);
      expect(cierre.hayPendienteDeSubir, isTrue,
          reason: 'pero el técnico tiene que saber que no llegó a la oficina');
    });

    test('Lo pendiente de subir no se confunde con lo pendiente de hacer', () {
      final cierre = evaluar(
        materiales: <Map<String, dynamic>>[{'estado': 'pendiente'}],
      );

      expect(cierre.bloqueantes, isEmpty);
      expect(cierre.hayPendienteDeSubir, isTrue);
    });
  });
}
