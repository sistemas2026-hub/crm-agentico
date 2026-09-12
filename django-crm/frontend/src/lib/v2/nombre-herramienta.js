/**
 * El nombre de una herramienta del asistente, legible.
 *
 * Vive aca y no junto al parser (`lib/server/v2/resumen-agente.js`) porque lo
 * necesitan los dos lados: el servidor al preparar los datos y la pantalla al
 * dibujarlos. Todo lo que cuelga de `lib/server/` es solo de servidor, y
 * duplicar la funcion para poder usarla en un componente deja dos copias que
 * se van a separar sin que nadie lo note.
 *
 * Solo cosmetico: guiones bajos a espacios y la primera en mayuscula. NO hay
 * un diccionario de herramienta -> frase bonita, y es deliberado -- cada
 * empresa declara sus propias herramientas, asi que un mapa aca cubriria las
 * de la primera y dejaria a las demas peor que sin el.
 *
 * @param {string} nombre
 * @returns {string}
 */
export function nombreLegible(nombre) {
  const limpio = (nombre ?? '').replace(/_/g, ' ').trim();
  return limpio ? limpio[0].toUpperCase() + limpio.slice(1) : '';
}
