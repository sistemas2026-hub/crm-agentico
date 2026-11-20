/// Qué dice el encabezado de «Mi Trabajo» debajo del título.
///
/// EL DEFECTO QUE ORIGINA ESTE ARCHIVO (09/11/2026)
/// ------------------------------------------------
/// La pantalla contaba `ordenes.trabajos.length` y lo rotulaba «N órdenes
/// asignadas para la jornada de hoy». Esa lista trae **todo lo que el teléfono
/// tiene descargado**, cerradas y canceladas incluidas, así que el número decía
/// una cosa y el rótulo afirmaba otra.
///
/// El usuario lo vio en su pantalla: «tiene el conteo total de las órdenes
/// asignadas, está combinando las cerradas y pendientes; solo tiene que mostrar
/// las asignadas hoy».
///
/// POR QUÉ ESTO ES LÓGICA PURA Y NO TRES LÍNEAS EN EL WIDGET
/// ---------------------------------------------------------
/// Porque es un número que una persona usa para saber cuánto le queda del día, y
/// un `.length` mal elegido no falla: muestra otra cifra, con la misma cara de
/// dato cierto. Acá se prueba sin emulador, sin base y sin red — el mismo
/// criterio de `cercania.dart` y `resumen_de_inicio.dart`.
///
/// LO QUE NO HACE
/// --------------
/// No decide qué órdenes son «de hoy»: eso lo resuelve quien llena la lista.
/// Acá se separa lo terminado de lo que falta, que es la distinción que el
/// rótulo estaba borrando.
library;

import 'estado_trabajo.dart';
import 'trabajo_vista.dart';

/// Las dos cifras del encabezado, ya decididas.
class ConteoDeMiTrabajo {
  const ConteoDeMiTrabajo({required this.asignadas, required this.terminadas});

  /// Cuántas órdenes tiene asignadas para la jornada.
  final int asignadas;

  /// De esas, cuántas ya terminó: completada, cerrada o cancelada. Sale de
  /// [EstadoTrabajo.terminada], que es la misma definición que usa el resto de
  /// la aplicación; si eso cambia, cambia acá solo.
  final int terminadas;

  /// Las que todavía le tocan. Nunca negativo: un dato raro en la base no
  /// puede producir «-1 por hacer» en la pantalla de alguien.
  int get porHacer => (asignadas - terminadas).clamp(0, asignadas);

  /// Cuenta sobre los trabajos que la pantalla ya tiene en la mano.
  factory ConteoDeMiTrabajo.de(List<TrabajoVista> trabajos) {
    final int total = trabajos.length;
    final int listas =
        trabajos.where((TrabajoVista t) => t.estado.terminada).length;
    return ConteoDeMiTrabajo(asignadas: total, terminadas: listas);
  }

  /// El renglón de debajo del título.
  ///
  /// «7 asignadas hoy · 4 cerradas». Las cerradas van aparte y no se suman al
  /// rótulo de asignadas: era justo la mezcla que se veía como un error de la
  /// aplicación. Cuando no hay ninguna terminada no se dice —«· 0 cerradas»
  /// ocupa lugar para informar que no pasó nada— y sin trabajos se dice eso,
  /// que no es lo mismo que un cero.
  String get linea {
    if (asignadas == 0) return 'Sin trabajos asignados para hoy';
    final String uno =
        asignadas == 1 ? '1 asignada hoy' : '$asignadas asignadas hoy';
    if (terminadas == 0) return uno;
    final String dos = terminadas == 1 ? '1 cerrada' : '$terminadas cerradas';
    return '$uno · $dos';
  }
}
