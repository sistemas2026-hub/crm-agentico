/**
 * «Fallas de red» — las caídas de PON vivas y el aviso a sus clientes
 * (30/10/2026, PRD §8.17, Ola 2).
 *
 * Server-only, por el mismo `apiRequest` que el resto del CRM. La regla vive en
 * el backend (`operaciones/aviso_de_caida.py`) y la lista la arma el motor: acá
 * no se decide a quién se le avisa.
 */
import { apiRequest } from '$lib/api-helpers.js';

const RUTA = '/operaciones/fallas-de-red/';

/** @param {{ cookies: any }} ctx */
export async function leerFallas(ctx) {
  return apiRequest(RUTA, {}, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id */
export async function prepararAviso(ctx, id) {
  return apiRequest(`${RUTA}${id}/aviso/`, { method: 'POST', body: { accion: 'preparar' } }, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id */
export async function aprobarAviso(ctx, id) {
  return apiRequest(`${RUTA}${id}/aviso/`, { method: 'POST', body: { accion: 'aprobar' } }, ctx);
}
