import { apiRequest } from '$lib/api-helpers.js';

/**
 * Lo que el Supervisor hace solo con el seguimiento, por empresa (30/10/2026):
 * recordarle al técnico la orden sin reporte, y cada cuánto vuelve a
 * recordárselo mientras sigue sin reportar (11/11/2026). Ver
 * campo/configuracion_de_seguimiento_views.py.
 *
 * Que CIERRE solo no se enciende acá: es una tarea que se le delega desde su
 * chat, con el nivel 3 y el interruptor de emergencia, como las otras.
 */

/** @param {{ cookies: any }} ctx */
export async function leerConfiguracionDeSeguimiento(ctx) {
  try {
    return { configuracion: await apiRequest('/campo/seguimiento/configuracion/', {}, ctx), error: false };
  } catch {
    return { configuracion: null, error: true };
  }
}

/**
 * Del formulario: una casilla marcada llega como 'on'; desmarcada, no llega.
 *
 * LOS MINUTOS LLEGAN COMO TEXTO, Y EL BACKEND EXIGE UN ENTERO (11/11/2026).
 * Un `<input type="number">` pone '15' en el FormData, no 15, y el PUT valida
 * `isinstance(v, int)`: mandar el texto da un 400 que dice «tienen que ser un
 * número entero» sobre un campo donde el usuario escribió un número, que es
 * el peor mensaje posible. Se convierte acá.
 *
 * Un campo vacío o con letras NO se manda: así el valor guardado queda como
 * estaba, en vez de pisarse con un 0 --que significa «avisar una sola vez»--
 * por un dedazo. La casilla sí viaja siempre, porque desmarcada tampoco llega
 * y su ausencia ES el apagado.
 *
 * @param {FormData} f
 */
export function cuerpoDeSeguimiento(f) {
  /** @type {{ recordar_al_tecnico: boolean, repetir_recordatorio_cada_minutos?: number }} */
  const cuerpo = { recordar_al_tecnico: f.get('recordar_al_tecnico') === 'on' };
  const crudo = f.get('repetir_recordatorio_cada_minutos');
  if (typeof crudo === 'string' && crudo.trim() !== '') {
    const n = Number(crudo);
    if (Number.isInteger(n)) cuerpo.repetir_recordatorio_cada_minutos = n;
  }
  return cuerpo;
}

/**
 * @param {{ cookies: any }} ctx
 * @param {{ recordar_al_tecnico: boolean, repetir_recordatorio_cada_minutos?: number }} cuerpo
 */
export async function guardarConfiguracionDeSeguimiento(ctx, cuerpo) {
  return apiRequest('/campo/seguimiento/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
