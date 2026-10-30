/**
 * El tablero de capacidad (30/10/2026, PRD §2 y §8.17 Ola 1): cuánto trabajo
 * le resolvió Dexter a la empresa, con sus contrapesos. Los números los
 * calcula el motor (nucleo/observabilidad/capacidad.py); acá solo se piden y
 * se pasan tal cual, con los mismos nombres. Ningún dato de un cliente.
 *
 * Server-only. No lanza: si el motor no contesta, devuelve el error.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/** Los períodos que ofrece la pantalla. Otro valor vuelve al de en medio. */
export const PERIODOS = [7, 30, 90];

/**
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {number} dias
 * @returns {Promise<{ tablero: any | null, error?: string }>}
 */
export async function leerTableroCapacidad(locals, fetch, dias) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return { tablero: null, error: 'Asistente no configurado para esta empresa.' };
  const q = new URLSearchParams({ tenant: cfg.tenant, dias: String(dias) });
  try {
    const resp = await fetch(`${cfg.baseUrl}/reportes/capacidad?${q}`, {
      headers: headersMotor(),
      signal: AbortSignal.timeout(20000)
    });
    const datos = await resp.json();
    if (!resp.ok) return { tablero: null, error: datos?.error || 'No se pudo calcular el tablero.' };
    return { tablero: datos };
  } catch {
    return { tablero: null, error: 'No se pudo contactar al asistente.' };
  }
}
