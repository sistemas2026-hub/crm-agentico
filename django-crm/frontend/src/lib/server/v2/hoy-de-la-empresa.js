/**
 * «Hoy» en el reloj de la EMPRESA, para las pantallas que abren en un día
 * (27/10/2026, hueco heredado de la 2.2 para la 3.1).
 *
 * El servidor de SvelteKit corre en UTC: `new Date().toISOString().slice(0, 10)`
 * da el día de Greenwich, y desde las 19:00 de Bogotá las pantallas del
 * Supervisor abrían en el día SIGUIENTE — el reparto de mañana, la capacidad
 * de mañana, las jornadas de mañana. Es el mismo error que el backend ya
 * corrigió con `campo.reparto._zona_de`, y se corrige con la misma zona:
 * `Org.timezone`, leída de `/api/org/settings/` (abierta a cualquier miembro).
 *
 * La zona se guarda 10 minutos por empresa: cambia una vez en la vida de una
 * empresa, y pedirla en cada pantalla sería una consulta más por carga. Un
 * fallo NO se guarda, y cae a UTC como el backend (`_zona_de`).
 */
import { apiRequest } from '$lib/api-helpers.js';

const GUARDAR_MS = 10 * 60 * 1000;

/** @type {Map<string, { zona: string, hasta: number }>} */
const zonas = new Map();

/**
 * El día (AAAA-MM-DD) que es en `zona` en el instante `ahora`. Una zona que
 * no existe cae a UTC.
 *
 * @param {string} zona
 * @param {Date} [ahora]
 */
export function diaEn(zona, ahora = new Date()) {
  try {
    //  en-CA escribe la fecha como AAAA-MM-DD.
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: zona || 'UTC',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    }).format(ahora);
  } catch {
    return ahora.toISOString().slice(0, 10);
  }
}

/**
 * La zona horaria de la empresa de quien mira.
 *
 * @param {{ org?: { id?: string } }} locals
 * @param {import('@sveltejs/kit').Cookies} cookies
 * @param {number} [ahora] milisegundos, para las pruebas
 */
export async function zonaDeLaEmpresa(locals, cookies, ahora = Date.now()) {
  const org = locals?.org?.id ?? '';
  const guardada = org ? zonas.get(org) : undefined;
  if (guardada && guardada.hasta > ahora) return guardada.zona;
  try {
    const r = await apiRequest('/org/settings/', {}, { cookies });
    const zona = String(r?.timezone ?? '').trim() || 'UTC';
    if (org) zonas.set(org, { zona, hasta: ahora + GUARDAR_MS });
    return zona;
  } catch {
    return 'UTC';
  }
}

/**
 * Hoy, AAAA-MM-DD, en el reloj de la empresa.
 *
 * @param {{ org?: { id?: string } }} locals
 * @param {import('@sveltejs/kit').Cookies} cookies
 */
export async function hoyDeLaEmpresa(locals, cookies) {
  return diaEn(await zonaDeLaEmpresa(locals, cookies));
}

/** Solo para las pruebas: olvida las zonas guardadas. */
export function _olvidarLasZonas() {
  zonas.clear();
}
