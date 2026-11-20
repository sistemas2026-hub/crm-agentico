/**
 * Hasta cuándo se espera (contrato v3.3, C22): la elección del compositor
 * convertida en una hora. Se calcula al ENVIAR, no al elegir: «en 1 h» es una
 * hora después de mandar la respuesta, no de abrir el selector.
 *
 * «Mañana 8:00» es la hora LOCAL de quien atiende, que es la del equipo: lo
 * que importa es que vuelva al empezar el turno.
 *
 * @param {string} eleccion  '', '1h', '4h' o 'manana'
 * @param {Date} [ahora]
 * @returns {string|null} ISO, o null sin hora
 */
export function horaDeEspera(eleccion, ahora = new Date()) {
  if (eleccion === '1h') return new Date(ahora.getTime() + 3600_000).toISOString();
  if (eleccion === '4h') return new Date(ahora.getTime() + 4 * 3600_000).toISOString();
  if (eleccion === 'manana') {
    const d = new Date(ahora);
    d.setDate(d.getDate() + 1);
    d.setHours(8, 0, 0, 0);
    return d.toISOString();
  }
  return null;
}
