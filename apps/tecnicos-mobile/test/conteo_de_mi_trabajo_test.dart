import 'package:campo/features/trabajo/conteo_de_mi_trabajo.dart';
import 'package:campo/features/trabajo/trabajo_vista.dart';
import 'package:flutter_test/flutter_test.dart';

/// EL ENCABEZADO DE «MI TRABAJO» (09/11/2026).
///
/// El defecto, visto por el usuario en su pantalla: la cifra salía de
/// `ordenes.trabajos.length` --todo lo descargado, cerradas y canceladas
/// incluidas-- y el rótulo decía «asignadas para la jornada de hoy». El número
/// no mentía solo; mentía el par número + rótulo, que es lo que se lee.
///
/// Se afirma sobre lo que la pantalla ESCRIBE, no sobre que exista un contador:
/// la frase entera es el efecto.
TrabajoVista _ot(String estado) => TrabajoVista.desdeOrden(<String, dynamic>{
      'id': 'ot-$estado',
      'numero': 1,
      'estado': estado,
      'cliente_nombre': 'Cliente',
      'direccion': 'Calle 1',
      'telefono': '',
      'tipo_nombre': 'Instalación',
      'tipo_codigo': 'ftth_instalacion',
      'schema_version': 1,
      'revision': 1,
      'diagnostico_previo_ia': '',
      'fecha_compromiso': null,
    });

void main() {
  group('El encabezado de Mi Trabajo', () {
    test('EL DEFECTO: las cerradas no se suman a lo asignado del día', () {
      final c = ConteoDeMiTrabajo.de(<TrabajoVista>[
        _ot('asignada'),
        _ot('en_sitio'),
        _ot('cerrada'),
        _ot('cerrada'),
        _ot('completada_campo'),
        _ot('cancelada'),
      ]);

      expect(c.asignadas, 6);
      expect(c.terminadas, 4);
      expect(c.porHacer, 2);
      expect(c.linea, '6 asignadas hoy · 4 cerradas');
    });

    test('sin ninguna terminada no dice «0 cerradas»', () {
      final c = ConteoDeMiTrabajo.de(<TrabajoVista>[
        _ot('asignada'),
        _ot('en_camino'),
      ]);
      expect(c.linea, '2 asignadas hoy');
      expect(c.porHacer, 2);
    });

    test('una sola de cada cosa va en singular', () {
      final c = ConteoDeMiTrabajo.de(<TrabajoVista>[_ot('asignada')]);
      expect(c.linea, '1 asignada hoy');

      final d = ConteoDeMiTrabajo.de(<TrabajoVista>[
        _ot('asignada'),
        _ot('cerrada'),
      ]);
      expect(d.linea, '2 asignadas hoy · 1 cerrada');
    });

    test('sin trabajos lo dice; un cero no es lo mismo', () {
      final c = ConteoDeMiTrabajo.de(const <TrabajoVista>[]);
      expect(c.linea, 'Sin trabajos asignados para hoy');
      expect(c.porHacer, 0);
    });

    /// Las devueltas para corregir y las detenidas LE TOCAN al técnico: no son
    /// trabajo terminado. Si entraran en «cerradas», el renglón diría que ya
    /// las resolvió.
    test('una devuelta y una detenida siguen contando como por hacer', () {
      final c = ConteoDeMiTrabajo.de(<TrabajoVista>[
        _ot('correccion_requerida'),
        _ot('bloqueada'),
        _ot('cerrada'),
      ]);
      expect(c.terminadas, 1);
      expect(c.porHacer, 2);
      expect(c.linea, '3 asignadas hoy · 1 cerrada');
    });

    /// `completada_pendiente_sync` es del teléfono: terminada en campo, todavía
    /// sin confirmar. Cuenta como terminada, porque para el técnico ya está
    /// hecha — lo que falta es que suba.
    test('la terminada que todavía no subió ya no le toca al técnico', () {
      final c = ConteoDeMiTrabajo.de(<TrabajoVista>[
        _ot('completada_pendiente_sync'),
        _ot('asignada'),
      ]);
      expect(c.terminadas, 1);
      expect(c.linea, '2 asignadas hoy · 1 cerrada');
    });

    test('un estado que esta versión no conoce no se da por terminado', () {
      final c = ConteoDeMiTrabajo.de(<TrabajoVista>[_ot('algo_nuevo')]);
      expect(c.terminadas, 0);
      expect(c.porHacer, 1);
    });

    /// Contando desde la lista esto no puede pasar --lo terminado es un
    /// subconjunto de lo asignado--, pero el constructor es público y un dato
    /// raro de la base entraría igual. Lo que no puede salir es «-1 por hacer»
    /// en la pantalla de alguien: un número negativo de trabajos se lee como
    /// una aplicación rota, y encima no dice cuál es el problema real.
    test('por hacer nunca es negativo, aunque los números no cierren', () {
      const c = ConteoDeMiTrabajo(asignadas: 2, terminadas: 5);
      expect(c.porHacer, 0);
    });
  });
}
