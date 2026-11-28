import { json } from '@sveltejs/kit';
import { search } from '$lib/server/v2/search.js';

/**
 * ⌘K palette search. The palette runs in the browser and the access token is an
 * httpOnly cookie, so the query is proxied through here; the cookie stays
 * server-side and the Django endpoint scopes results to the caller's org.
 *
 * Desde el 12/11/2026 también busca en las conversaciones (el motor), con el
 * tenant de la sesión: por eso viajan `locals` y `fetch`, y la señal del
 * pedido, para que una tecla nueva corte la búsqueda anterior en el motor.
 * Sin sesión no se busca nada. El error no lleva el texto del backend: `q`
 * puede ser un teléfono, y la paleta ya dice qué fuente no contestó.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, cookies, locals, fetch, request }) {
  if (!locals.user) return json({ results: [], incompletas: [] }, { status: 401 });
  const q = url.searchParams.get('q') || '';
  try {
    return json(await search({ cookies, locals, fetch, signal: request.signal }, q));
  } catch {
    return json({ results: [], incompletas: ['la búsqueda'], error: 'Falló la búsqueda' }, { status: 502 });
  }
}
