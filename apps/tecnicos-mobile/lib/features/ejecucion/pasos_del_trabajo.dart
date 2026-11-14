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

/// Lo que un paso dice de sí mismo cuando NO es el que se está llenando.
///
/// EL PEDIDO (14/11/2026)
/// ----------------------
/// El usuario, con la pantalla de una instalación delante: «es muy confuso
/// para el técnico; tiene que [ser] un tipo formulario para que sea más fácil
/// y que muestre lo que está llenado».
///
/// Hasta hoy un paso cerrado era un círculo con un número. El técnico sabía
/// que había pasado por ahí y no qué había dejado adentro, así que para
/// comprobarlo tenía que volver a entrar -- y con cinco pasos eso es cinco
/// viajes para contestar «¿ya puse el serial?».
///
/// QUÉ DEVUELVE
/// ------------
/// Una línea corta. Lo que está lleno, y si falta algo, cuánto:
///
///     'Puerto 7 · CTO-SOL-114 · 2 fotos'
///     'Serial HWTC8A3F21B4 · faltan 2 fotos'
///     'faltan 3 datos'
///     ''                                   (el paso no pide nada)
///
/// LOS VALORES SE MUESTRAN, NO SE INTERPRETAN. No se traduce «true» a «sí» ni
/// se redondea un número: lo que el técnico escribió es lo que tiene que
/// leer, o el resumen deja de servir para comprobar.
///
/// CUÁNTOS VALORES: tres. Con todos, la línea pasa de un renglón en un
/// teléfono y se corta en cualquier lado; con uno, no alcanza para reconocer
/// el paso. Los que no entran se cuentan al final.
String resumenDelPaso({
  required List<String> etiquetas,
  required List<String> valores,
  required int camposVacios,
  required int fotosPuestas,
  required int fotosQueFaltan,
  int cuantosValores = 3,
}) {
  final List<String> partes = <String>[];

  final int tope = cuantosValores < 0 ? 0 : cuantosValores;
  int mostrados = 0;
  for (int i = 0; i < valores.length && mostrados < tope; i++) {
    final String v = valores[i].trim();
    if (v.isEmpty) continue;
    final String e = i < etiquetas.length ? etiquetas[i].trim() : '';
    //  La etiqueta ADELANTE y corta: «Puerto 7» se lee; «7» solo, no. Pero si
    //  la etiqueta es larga ocupa el renglón entero, así que ahí gana el valor.
    partes.add(e.isNotEmpty && e.length <= 14 ? '$e $v' : v);
    mostrados++;
  }

  final int sinMostrar = valores.where((String v) => v.trim().isNotEmpty).length - mostrados;
  if (sinMostrar > 0) partes.add('+$sinMostrar');

  if (fotosPuestas > 0) {
    partes.add(fotosPuestas == 1 ? '1 foto' : '$fotosPuestas fotos');
  }

  //  LO QUE FALTA VA AL FINAL Y SE NOMBRA. Un paso a medias que solo muestre
  //  lo que tiene se lee como terminado.
  final List<String> faltan = <String>[];
  if (camposVacios > 0) {
    faltan.add(camposVacios == 1 ? '1 dato' : '$camposVacios datos');
  }
  if (fotosQueFaltan > 0) {
    faltan.add(fotosQueFaltan == 1 ? '1 foto' : '$fotosQueFaltan fotos');
  }
  if (faltan.isNotEmpty) partes.add('faltan ${faltan.join(' y ')}');

  return partes.join(' · ');
}
