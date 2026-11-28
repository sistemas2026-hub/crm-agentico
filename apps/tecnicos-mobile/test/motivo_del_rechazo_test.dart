import 'package:flutter_test/flutter_test.dart';
import 'package:campo/core/sync/motivo_del_rechazo.dart';

/// LO QUE ESTAS PRUEBAS AFIRMAN, Y POR QUE ASI  --  10/11/2026.
///
/// Afirman que el motivo que el servidor manda LLEGA, nombrando el campo. No
/// afirman la redacción: el servidor puede cambiar una frase y eso no es una
/// regresión. Lo que no puede pasar es que el campo se pierda, porque es lo
/// único que le sirve al técnico para arreglarlo.
///
/// Los cuerpos de abajo son los del backend REAL, copiados de
/// `campo/views.py` y `campo/services/validador.py`. Si el backend cambia una
/// forma, esta prueba se pone roja acá y no en el teléfono de alguien.
void main() {
  group('A · el 400 de validación', () {
    test('a1 · el campo que no existe en la plantilla llega con su nombre', () {
      //  La forma exacta de `validar_campos_tecnicos` + `views.py`.
      final motivo = motivoDelRechazo(<String, Object?>{
        'guardado': false,
        'errores': <String, Object?>{
          'potencia_rx': "El campo 'potencia_rx' no existe en la plantilla de "
              'este trabajo.',
        },
      }, respaldo: 'Http status error [400]');

      //  EL EFECTO: el nombre del campo está. Es lo que hace accionable el
      //  aviso, y es exactamente lo que se perdía.
      expect(motivo, contains('potencia_rx'));
      expect(motivo, contains('no existe en la plantilla'));
      //  Y NO quedó el mensaje genérico de Dio, que es lo que se guardaba.
      expect(motivo, isNot(contains('Http status error')));
    });

    test('a2 · varios campos se dicen todos, no solo el primero', () {
      final motivo = motivoDelRechazo(<String, Object?>{
        'guardado': false,
        'errores': <String, Object?>{
          'potencia_rx': 'Valor no corresponde al tipo numero: x',
          'firma': "El campo 'firma' no existe en la plantilla de este trabajo.",
        },
      });
      expect(motivo, contains('potencia_rx'));
      expect(motivo, contains('firma'));
    });

    test('a3 · el nombre del campo no se dice dos veces', () {
      //  La frase de este backend ya nombra el campo. Anteponer la clave
      //  daría «potencia_rx: El campo 'potencia_rx' no existe…».
      final motivo = motivoDelRechazo(<String, Object?>{
        'errores': <String, Object?>{
          'potencia_rx': "El campo 'potencia_rx' no existe en la plantilla.",
        },
      });
      expect('potencia_rx'.allMatches(motivo).length, 1,
          reason: 'una vez, no dos: $motivo');
    });

    test('a4 · la lista del checklist también llega', () {
      //  `verificar_checklist_completo` devuelve una LISTA de objetos.
      final motivo = motivoDelRechazo(<String, Object?>{
        'errores': <Object?>[
          <String, Object?>{
            'codigo': 'CAMPO_FALTANTE',
            'campo_id': 'firma',
            'mensaje': "El campo técnico 'Firma del cliente' es obligatorio.",
          },
        ],
      });
      expect(motivo, contains('Firma del cliente'));
      expect(motivo, contains('obligatorio'));
    });
  });

  group('B · el 409 de concurrencia', () {
    test('b1 · los campos que chocaron llegan, no solo el código', () {
      //  La forma exacta de `GuardarDatosTrabajoView.patch`.
      final motivo = motivoDelRechazo(<String, Object?>{
        'error': 'STALE_WORK_ORDER',
        'detalle': "Conflicto de concurrencia en campos: ['potencia_rx']. "
            'La orden fue modificada en el servidor.',
        'revision_actual': 7,
      });

      //  EL EFECTO: el campo que chocó. Antes se guardaba la palabra
      //  `STALE_WORK_ORDER` sola, que no dice en qué chocó ni con qué.
      expect(motivo, contains('potencia_rx'));
      expect(motivo, contains('modificada en el servidor'));
    });

    test('b2 · sin detalle, queda el código y no un vacío', () {
      final motivo = motivoDelRechazo(<String, Object?>{
        'error': 'OPERACION_EN_CURSO',
      });
      expect(motivo, contains('OPERACION_EN_CURSO'));
    });

    test('b3 · la revisión no se lee como un motivo', () {
      //  `revision_actual` acompaña el rechazo; «revision_actual: 7» no le
      //  dice nada a nadie.
      final motivo = motivoDelRechazo(<String, Object?>{'revision_actual': 7});
      expect(motivo, isNot(contains('revision_actual')));
    });
  });

  group('C · lo plano de DRF', () {
    test('c1 · el serializer que corta antes de la vista llega con su campo',
        () {
      //  `serializer.is_valid(raise_exception=True)` devuelve esto, sin
      //  ninguna clave `error` ni `errores`.
      final motivo = motivoDelRechazo(<String, Object?>{
        'revision_base': <Object?>['This field is required.'],
      });
      expect(motivo, contains('revision_base'));
      expect(motivo, contains('required'));
    });
  });

  group('D · cuando el cuerpo no dice nada', () {
    test('d1 · se guarda el respaldo, que al menos distingue un timeout', () {
      expect(motivoDelRechazo(null, respaldo: 'Se agotó el tiempo de espera.'),
          'Se agotó el tiempo de espera.');
      expect(motivoDelRechazo(<String, Object?>{'guardado': false},
              respaldo: 'Se agotó el tiempo de espera.'),
          'Se agotó el tiempo de espera.');
    });

    test('d2 · sin cuerpo y sin respaldo, lo dice en vez de quedar en blanco',
        () {
      //  Una cadena vacía en la base local se lee como «no pasó nada», que es
      //  justo lo contrario de lo que pasó.
      final motivo = motivoDelRechazo(null);
      expect(motivo.trim(), isNotEmpty);
      expect(motivo, contains('rechazó'));
    });

    test('d3 · una página HTML de error no se guarda entera', () {
      //  Un 500 de nginx devuelve HTML. No es un motivo, pero tampoco puede
      //  llenar la base del teléfono.
      final motivo = motivoDelRechazo('<html>${'x' * 2000}</html>');
      expect(motivo.length, lessThanOrEqualTo(400));
      expect(motivo, endsWith('…'));
    });
  });
}
