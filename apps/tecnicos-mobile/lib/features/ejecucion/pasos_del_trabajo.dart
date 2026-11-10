/// QUÉ SE VE EN CADA PASO DEL TRABAJO (09/11/2026).
///
/// EL PEDIDO
/// ---------
/// El usuario, sobre la pantalla de ejecución: «donde sale 1 diagnóstico, 2
/// solución, 3 otros datos: hacer que la interfaz sea más creativa; si le dan
/// en 1 diagnóstico, que solo le muestre lo que está en diagnóstico. Quitar la
/// comprobación de conexión y materiales en esta orden; esos campos que solo
/// salgan en solución».
///
/// LO QUE PASABA
/// -------------
/// Los pasos ordenaban los CAMPOS, pero debajo del paso seguían dibujándose
/// siempre dos bloques más: «Comprobar conexión» y «Materiales en esta orden».
/// Así, parado en el paso 1, el técnico veía su diagnóstico y además dos cosas
/// que no le tocan todavía -- y el paso dejaba de significar algo, porque
/// igual había que bajar por todo.
///
/// POR QUÉ ESTO ES LÓGICA PURA
/// ---------------------------
/// Porque «en qué paso se ve qué» es una regla del trabajo, no un detalle de
/// dibujo: si se equivoca, alguien registra el material en el paso donde
/// todavía no sabe cuánto usó, o comprueba la conexión antes de haber tocado
/// nada. Acá se prueba sin emulador.
library;

/// Si en este paso van los bloques del final: comprobar la conexión y el
/// material usado.
///
/// EL ÚLTIMO, y no «el que se llame Solución». Buscar la palabra funcionaría
/// hasta que una empresa escriba «Reparación» o «Cierre» en su plantilla, y
/// entonces esos dos bloques desaparecerían sin que nadie lo note. El último
/// paso es el último en cualquier plantilla, y es donde el trabajo ya está
/// hecho: es cuando se sabe qué material se usó y cuando comprobar la conexión
/// dice algo.
///
/// Con un solo paso --o sin pasos-- van ahí: no hay ningún otro lugar.
bool esElPasoDeCierre({required int indice, required int total}) {
  if (total <= 1) return true;
  return indice >= total - 1;
}

/// En qué estado se dibuja el círculo de un paso en la línea de arriba.
EstadoDelPaso estadoDelPaso({
  required int indice,
  required int actual,
  required bool completo,
}) {
  if (indice == actual) return EstadoDelPaso.enCurso;
  //  Completo gana sobre «ya pasé por él»: lo que importa es si le falta algo,
  //  no por dónde anduvo el técnico. Un paso que quedó a medias y se dejó
  //  atrás tiene que seguir viéndose incompleto.
  if (completo) return EstadoDelPaso.hecho;
  return EstadoDelPaso.pendiente;
}

enum EstadoDelPaso {
  /// Ya tiene todo lo que pedía.
  hecho,

  /// Donde está parado el técnico ahora.
  enCurso,

  /// Todavía le falta algo, esté antes o después del actual.
  pendiente,
}
