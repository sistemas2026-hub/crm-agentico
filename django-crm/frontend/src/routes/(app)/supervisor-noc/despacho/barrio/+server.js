import { json } from '@sveltejs/kit';
import { leerZonasConocidas } from '$lib/server/v2/cuadrillas.js';

/**
 * ¿El barrio escrito está mapeado a una zona, y si no, a cuál se parece?
 * (13/10/2026). Lo pregunta Despacho al salir del campo «Barrio».
 *
 * NO ES UN PROXY ABIERTO: una sola pregunta, de solo lectura, y la respuesta
 * sale tal cual del backend, que es el único que decide qué se parece.
 */

/** @type {import('./$types').RequestHandler} */
export async function GET({ url, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró.' }, { status: 401 });
  }
  const q = (url.searchParams.get('q') ?? '').trim();
  if (!q) return json({ exacta: null, parecidas: [] });
  const r = await leerZonasConocidas({ cookies }, q);
  if (r.error) return json({ error: 'No se pudo consultar.' }, { status: 502 });
  return json({ exacta: r.exacta, parecidas: r.parecidas });
}
