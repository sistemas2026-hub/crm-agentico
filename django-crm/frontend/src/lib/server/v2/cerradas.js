/**
 * Las órdenes cerradas en unos días (30/10/2026): `GET /api/campo/cerradas/`,
 * la pestaña Cerradas de Programación. Ver `campo/ordenes_cerradas.py`.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * @param {{ cookies: any }} ctx
 * @param {string} desde AAAA-MM-DD
 * @param {string} hasta AAAA-MM-DD
 * @returns {Promise<{ cerradas: any, error: boolean }>}
 */
export async function leerCerradas(ctx, desde, hasta) {
  try {
    const q = new URLSearchParams({ desde, hasta });
    return { cerradas: await apiRequest(`/campo/cerradas/?${q}`, {}, ctx), error: false };
  } catch {
    return { cerradas: null, error: true };
  }
}
