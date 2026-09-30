import 'package:campo/features/ejecucion/campo_del_formulario.dart';
import 'package:flutter_test/flutter_test.dart';

/// Una sola lectura del formulario dinámico.
///
/// LO QUE CUIDAN ESTAS PRUEBAS
/// ---------------------------
/// Que el formulario que se dibuja, el checklist de cierre y la validación
/// entiendan **lo mismo** por el mismo campo.
///
/// Antes no era así, y las dos discrepancias se reforzaban: un campo de
/// selección del servidor salía con "Sin opciones definidas" —porque el widget
/// buscaba `opciones` y el backend manda `reglas.options`— y además la
/// validación no lo contaba como obligatorio —porque leía `obligatorio` y el
/// backend manda `reglas.required`—. Resultado: un campo que no se podía
/// responder y que tampoco se pedía. El dato no llegaba nunca.
void main() {
  /// Como lo manda el servidor hoy (`campo/services/validador.py`).
  Map<String, dynamic> delServidor({
    String tipo = 'seleccion',
    bool required = true,
    List<String>? options,
    double? min,
    double? max,
  }) =>
      <String, dynamic>{
        'id': 'tipo_intervencion',
        'titulo': 'Tipo de intervención física',
        'tipo': tipo,
        'ayuda': 'Seleccioná el tramo intervenido.',
        'reglas': <String, dynamic>{
          'required': required,
          'options': ?options,
          'min': ?min,
          'max': ?max,
        },
      };

  /// El formato viejo, que todavía vive en órdenes ya guardadas.
  Map<String, dynamic> delFormatoViejo() => <String, dynamic>{
        'clave': 'tipo_intervencion',
        'etiqueta': 'Tipo de intervención física',
        'tipo': 'seleccion',
        'obligatorio': true,
        'opciones': <String>['Acometida / Drop', 'Roseta / Conector'],
      };

  group('1. El formato del servidor', () {
    test('Las opciones salen de reglas.options', () {
      // El defecto original: se buscaban en `opciones` y nunca aparecían.
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['Acometida / Drop', 'Roseta / Conector']),
        <String, dynamic>{},
      );

      expect(campo.opciones, <String>['Acometida / Drop', 'Roseta / Conector']);
      expect(campo.estado, EstadoDeCampo.pendiente);
    });

    test('Es obligatorio por reglas.required', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['A', 'B']),
        <String, dynamic>{},
      );

      expect(campo.obligatorio, isTrue);
      expect(campo.bloqueaCierre, isTrue);
    });

    test('El id y el título son los del servidor', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['A']),
        <String, dynamic>{},
      );

      expect(campo.id, 'tipo_intervencion');
      expect(campo.titulo, 'Tipo de intervención física');
    });
  });

  group('2. El formato viejo sigue funcionando', () {
    test('Una orden guardada antes se abre igual', () {
      // A alguien que ya tiene la orden en el teléfono no se le puede pedir
      // que resincronice para poder trabajar.
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delFormatoViejo(),
        <String, dynamic>{},
      );

      expect(campo.id, 'tipo_intervencion');
      expect(campo.titulo, 'Tipo de intervención física');
      expect(campo.obligatorio, isTrue);
      expect(campo.opciones, hasLength(2));
    });

    test('Los dos formatos dan exactamente lo mismo', () {
      final CampoDelFormulario nuevo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['Acometida / Drop', 'Roseta / Conector']),
        <String, dynamic>{},
      );
      final CampoDelFormulario viejo = CampoDelFormulario.desdeEsquema(
        delFormatoViejo(),
        <String, dynamic>{},
      );

      expect(nuevo.id, viejo.id);
      expect(nuevo.titulo, viejo.titulo);
      expect(nuevo.obligatorio, viejo.obligatorio);
      expect(nuevo.opciones, viejo.opciones);
      expect(nuevo.estado, viejo.estado);
      expect(nuevo.bloqueaCierre, viejo.bloqueaCierre);
    });
  });

  group('3. El estado de la respuesta', () {
    test('Sin responder, pendiente', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['A', 'B']),
        <String, dynamic>{},
      );

      expect(campo.estado, EstadoDeCampo.pendiente);
      expect(campo.bloqueaCierre, isTrue);
    });

    test('Respondido, completo, y deja cerrar', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['A', 'B']),
        <String, dynamic>{'tipo_intervencion': 'A'},
      );

      expect(campo.estado, EstadoDeCampo.completo);
      expect(campo.bloqueaCierre, isFalse);
    });

    test('Sólo espacios sigue siendo pendiente', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['A', 'B']),
        <String, dynamic>{'tipo_intervencion': '   '},
      );

      expect(campo.estado, EstadoDeCampo.pendiente);
    });

    test('Una selección sin opciones es un error, no un vacío', () {
      // Es un problema de la plantilla, no del técnico: no se puede responder
      // por más que quiera, así que decirle "falta completar" sería mentirle.
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(),
        <String, dynamic>{},
      );

      expect(campo.estado, EstadoDeCampo.error);
      expect(campo.motivoDelError, contains('sin opciones'));
      expect(campo.motivoDelError, contains('oficina'),
          reason: 'tiene que decir a quién avisar');
      expect(campo.bloqueaCierre, isTrue);
    });

    test('Una opción que ya no está en la lista es un error', () {
      // Pasa cuando la plantilla cambia con la respuesta ya guardada.
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        delServidor(options: <String>['A', 'B']),
        <String, dynamic>{'tipo_intervencion': 'C'},
      );

      expect(campo.estado, EstadoDeCampo.error);
    });
  });

  group('4. Los números respetan el rango del esquema', () {
    Map<String, dynamic> medicion() => <String, dynamic>{
          'id': 'potencia_rx',
          'titulo': 'Potencia óptica',
          'tipo': 'decimal',
          'unidad': 'dBm',
          'reglas': <String, dynamic>{
            'required': true,
            'min': -30.0,
            'max': -5.0,
          },
        };

    test('Dentro del rango, completo', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        medicion(),
        <String, dynamic>{'potencia_rx': '-18.4'},
      );

      expect(campo.estado, EstadoDeCampo.completo);
      expect(campo.minimo, -30.0);
      expect(campo.maximo, -5.0);
    });

    test('Fuera del rango bloquea el cierre, aunque tenga valor', () {
      // Un número imposible se firma igual que uno bueno: es peor que un
      // vacío, porque nadie lo vuelve a mirar.
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        medicion(),
        <String, dynamic>{'potencia_rx': '-45'},
      );

      expect(campo.estado, EstadoDeCampo.error);
      expect(campo.bloqueaCierre, isTrue);
    });

    test('Un texto donde va un número también', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        medicion(),
        <String, dynamic>{'potencia_rx': 'no medí'},
      );

      expect(campo.estado, EstadoDeCampo.error);
      expect(campo.motivoDelError, contains('número'));
    });
  });

  group('5. Casos que no pueden tumbar la pantalla', () {
    test('Un booleano sin responder cuenta como completo', () {
      // El interruptor siempre muestra una de las dos posiciones: no hay un
      // estado "sin tocar" que el técnico pueda ver.
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        <String, dynamic>{
          'id': 'reemplazo',
          'titulo': '¿Se reemplazó el equipo?',
          'tipo': 'booleano',
          'reglas': <String, dynamic>{'required': true},
        },
        <String, dynamic>{},
      );

      expect(campo.estado, EstadoDeCampo.completo);
      expect(campo.bloqueaCierre, isFalse);
    });

    test('Un tipo desconocido se trata como texto y no se pierde', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        <String, dynamic>{
          'id': 'algo_nuevo',
          'titulo': 'Campo de una versión más nueva',
          'tipo': 'geolocalizacion',
        },
        <String, dynamic>{'algo_nuevo': '6.25, -75.56'},
      );

      expect(campo.estado, EstadoDeCampo.completo);
      expect(campo.titulo, 'Campo de una versión más nueva');
    });

    test('Un esquema con basura no tumba la lista', () {
      final List<CampoDelFormulario> campos = CampoDelFormulario.normalizar(
        <dynamic>[
          delServidor(options: <String>['A']),
          'esto no es un campo',
          null,
          42,
        ],
        <String, dynamic>{},
      );

      expect(campos, hasLength(1),
          reason: 'lo que no es un mapa se descarta sin romper nada');
    });

    test('Un campo sin id ni clave no explota', () {
      final CampoDelFormulario campo = CampoDelFormulario.desdeEsquema(
        <String, dynamic>{'titulo': 'Huérfano', 'tipo': 'texto'},
        <String, dynamic>{},
      );

      expect(campo.id, isEmpty);
      expect(campo.titulo, 'Huérfano');
    });
  });
}
