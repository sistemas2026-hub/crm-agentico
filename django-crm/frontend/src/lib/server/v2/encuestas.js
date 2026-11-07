/**
 * «Calidad de la atención» (28/10/2026): lo que contestaron los clientes en la
 * encuesta de WhatsApp al cerrar su caso. Los números los calcula el motor
 * (nucleo/persistencia/encuestas.py::resumir), donde viven las encuestas; acá
 * solo se piden. Sin datos del cliente: caso, opción, puntaje, responsable.
 *
 * Server-only. No lanza: si el motor no contesta, la pantalla lo dice.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {{ desde: string, hasta: string }} periodo AAAA-MM-DD, `hasta` incluido
 * @returns {Promise<any | null>}
 */
export async function leerResumenEncuestas(locals, fetch, periodo) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  const q = new URLSearchParams({ tenant: cfg.tenant, desde: periodo.desde, hasta: periodo.hasta });
  try {
    const resp = await fetch(`${cfg.baseUrl}/encuestas/resumen?${q}`, {
      headers: headersMotor(),
      signal: AbortSignal.timeout(10000)
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}
