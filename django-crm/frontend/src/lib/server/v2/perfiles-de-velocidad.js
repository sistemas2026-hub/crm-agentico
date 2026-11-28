/**
 * El ancho de banda de cada plan en la red (27/11/2026).
 *
 * El usuario: «en SmartOLT también hay que ponerle el ancho de banda de
 * descarga y carga». Al activar la ONU de una instalación se le pone el perfil
 * de bajada y el de subida del plan del contrato. Qué perfil va con qué plan es
 * una decisión de la empresa (CLAUDE.md §3.3): se elige en Programación → El
 * contrato de instalación, y se guarda con el contrato (backend).
 *
 * La lista de perfiles y la sugerencia por plan las da el motor, que es el que
 * habla con el proveedor de la red: GET /configuracion/perfiles-de-velocidad en
 * nucleo/canales/api.py. Solo lee. Lo que se muestra y se guarda de la tabla
 * está en $lib/supervisor/perfiles-de-velocidad.js (puro).
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/** @typedef {import('$lib/supervisor/perfiles-de-velocidad.js').Perfiles} Perfiles */

/**
 * Lo que dice el motor. `null` si no contesta: la pantalla lo dice y NO
 * muestra la tabla, para que un guardado no la borre.
 * @param {any} locals @param {typeof fetch} fetch
 * @returns {Promise<Perfiles | null>}
 */
export async function leerPerfiles(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const r = await fetch(
      `${cfg.baseUrl}/configuracion/perfiles-de-velocidad?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}
