/**
 * Pedir la traza de un turno del simulador hasta que esté completa
 * (12/11/2026).
 *
 * El motor escribe la traza en un hilo un instante DESPUÉS de responder
 * (nucleo/canales/api.py::_guardar_traza). Si la pantalla pregunta enseguida,
 * puede recibir media traza o ninguna; el motor dice `completa` cuando el
 * cierre del turno ya quedó escrito (va en la misma transacción que la traza).
 *
 * Por eso se vuelve a preguntar mientras `completa` sea false, con un tope:
 * pasado el tope se muestra lo que haya, marcado como incompleto, en vez de
 * esperar para siempre o afirmar «no llamó a ninguna herramienta» sin saberlo.
 */

export const INTENTOS = 6;
export const ESPERA_MS = 700;

/**
 * @param {(url: string) => Promise<Response>} pedir
 * @param {string} conversacion
 * @param {string} desde  el mensaje del cliente que abrió el turno
 * @param {{ intentos?: number, esperaMs?: number,
 *           dormir?: (ms: number) => Promise<void> }} [opciones]
 * @returns {Promise<{completa: boolean, herramientas: any[], derivo_a: string|null,
 *                    errores: any[], error?: string}>}
 */
export async function esperarTraza(pedir, conversacion, desde, opciones = {}) {
  const intentos = opciones.intentos ?? INTENTOS;
  const esperaMs = opciones.esperaMs ?? ESPERA_MS;
  const dormir = opciones.dormir ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
  const url = `/api/simulador-whatsapp/traza?conversacion=${encodeURIComponent(conversacion)}`
    + `&desde=${encodeURIComponent(desde)}`;

  /** @type {any} */
  let ultima = null;
  for (let i = 0; i < intentos; i++) {
    if (i > 0) await dormir(esperaMs);
    try {
      const resp = await pedir(url);
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        // Un 4xx no se arregla esperando: se dice y se corta.
        return { completa: false, herramientas: [], derivo_a: null, errores: [],
          error: datos.error || 'No se pudo leer la traza.' };
      }
      ultima = datos;
      if (datos.completa) return datos;
    } catch {
      // Un fallo de red puntual: el intento siguiente lo resuelve.
    }
  }
  return {
    completa: false,
    herramientas: ultima?.herramientas ?? [],
    derivo_a: ultima?.derivo_a ?? null,
    errores: ultima?.errores ?? [],
    ...(ultima ? {} : { error: 'No se pudo leer la traza.' })
  };
}
