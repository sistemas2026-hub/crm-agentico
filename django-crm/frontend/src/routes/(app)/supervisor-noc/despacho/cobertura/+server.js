import { json } from '@sveltejs/kit';
import { leerCobertura } from '$lib/server/v2/despacho.js';

/**
 * A qué zona va el barrio y qué cuadrilla la cubre ese día (13/10/2026).
 * Lo pregunta Despacho cuando cambian el barrio, la plantilla o la fecha.
 *
 * NO ES UN PROXY ABIERTO: una sola pregunta, de solo lectura; la respuesta sale
 * tal cual del backend, que aplica la misma regla que el reparto.
 */

/** @type {import('./$types').RequestHandler} */
export async function GET({ url, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró.' }, { status: 401 });
  }
  const r = await leerCobertura({ cookies }, {
    barrio: (url.searchParams.get('barrio') ?? '').trim(),
    fecha: (url.searchParams.get('fecha') ?? '').trim(),
    labor: (url.searchParams.get('labor') ?? '').trim()
  });
  if (!r) return json({ error: 'No se pudo consultar.' }, { status: 502 });
  return json(r);
}
