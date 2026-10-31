import 'package:campo/features/detalle_orden/pasos_orden.dart';
import 'package:campo/features/trabajo/estado_trabajo.dart';
import 'package:flutter_test/flutter_test.dart';

/// El estado que la aplicación no conocía, y lo que eso rompía.
///
/// LO QUE SE MIDIÓ EN EL EMULADOR (02/10/2026)
/// -------------------------------------------
/// La Fase C agregó `bloqueada` al backend. Esta aplicación nunca aprendió ese
/// nombre, así que caía en `desconocido`, y `desconocido` significa «no sé qué
/// es esto»: la orden aparecía como **«Estado desconocido»**, con **«PASO 0 DE
/// 5»** —como si el trabajo no hubiera empezado nunca, estando el técnico en el
/// sitio— y sin ninguna acción.
///
/// Un trabajo detenido es de los que MÁS le toca al técnico: es justamente el
/// que hay que destrabar. La aplicación lo trataba como si no existiera.
///
/// LAS TRES AFIRMACIONES
/// ---------------------
/// 1. El nombre del backend se reconoce.
/// 2. **No retrocede el paso.** El bloqueo no deshace nada —el backend guarda el
///    estado al que se vuelve— así que la barra tiene que seguir donde estaba.
/// 3. **No ofrece acciones de la máquina de estados**, y eso NO es un olvido:
///    es la razón por la que la salida del bloqueo vive en la ficha. Con el
///    trabajo detenido no hay «Ejecutar el trabajo»; si destrabar viviera en la
///    pantalla de ejecución, un trabajo bloqueado sería un callejón sin salida.
void main() {
  group('1. La app reconoce el estado que el backend escribe', () {
    test('«bloqueada» ya no cae en desconocido', () {
      expect(EstadoTrabajo.desde('bloqueada'), EstadoTrabajo.bloqueada);
    });

    test('y se llama en pantalla como lo que es', () {
      expect(EstadoTrabajo.bloqueada.etiqueta, 'Detenida');
      expect(EstadoTrabajo.bloqueada.etiqueta, isNot('Estado desconocido'));
    });

    test('un nombre que de verdad no existe SIGUE cayendo en desconocido', () {
      // La otra dirección: aceptar cualquier cosa habría sido peor que no
      // conocer «bloqueada».
      expect(EstadoTrabajo.desde('inventado'), EstadoTrabajo.desconocido);
    });

    test('cuenta como trabajo pendiente del técnico', () {
      // Es el que hay que destrabar: si no contara, el número de la barra
      // inferior le diría que no le queda nada.
      expect(EstadoTrabajo.bloqueada.leTocaAlTecnico, isTrue);
      expect(EstadoTrabajo.bloqueada.terminada, isFalse);
    });
  });

  group('2. Detenida no hace retroceder el trabajo', () {
    test('la barra se queda en el sitio, no vuelve a cero', () {
      final LecturaDePasos lectura = LecturaDePasos.de(EstadoTrabajo.bloqueada);

      expect(lectura.pasoActual, 2);
      // El valor que tenía antes de este arreglo, por caer en `desconocido`.
      expect(lectura.pasoActual, isNot(0));
    });

    test('se dice que está detenida y cómo sigue', () {
      final LecturaDePasos lectura = LecturaDePasos.de(EstadoTrabajo.bloqueada);

      expect(lectura.excepcion, isTrue);
      expect(lectura.avisoExcepcion, isNotNull);
      expect(lectura.avisoExcepcion, contains('detenido'));
    });
  });

  group('3. Detenida no ofrece acciones, y por eso destrabar vive en la ficha', () {
    test('la máquina de estados no da ninguna', () {
      final AccionesDisponibles acciones = AccionesDisponibles.para(
        EstadoTrabajo.bloqueada,
      );

      expect(acciones.primaria, isNull);
      expect(acciones.secundarias, isEmpty);
    });

    test('mientras que en sitio SÍ da, que es el contraste', () {
      // Sin esto, una implementación que devolviera `ninguna` para todo
      // cumpliría la prueba de arriba.
      final AccionesDisponibles acciones = AccionesDisponibles.para(
        EstadoTrabajo.enSitio,
      );

      expect(acciones.primaria, isNotNull);
    });
  });
}
