/**
 * Lo que quedó publicado un día (28/10/2026): `GET /api/campo/dia-publicado/`,
 * la pantalla de Programación. Ver `campo/dia_publicado.py`.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * @param {{ cookies: any }} ctx
 * @param {string} dia AAAA-MM-DD
 * @returns {Promise<{ publicado: any, error: boolean }>}
 */
export async function leerDiaPublicado(ctx, dia) {
  try {
    const d = await apiRequest(`/campo/dia-publicado/?fecha=${encodeURIComponent(dia)}`, {}, ctx);
    return { publicado: d, error: false };
  } catch {
    return { publicado: null, error: true };
  }
}
