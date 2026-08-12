import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Los ejemplos ya marcados, para la pantalla /manual. Proxy de solo lectura
 * hacia nucleo/canales/api.py:GET /manual/ejemplos. Reenvia '?caso=' tal
 * cual si vino (sin ese parametro, el motor trae todos los casos juntos).
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const caso = url.searchParams.get('caso');
  const query = new URLSearchParams({ tenant });
  if (caso) query.set('caso', caso);

  try {
    const resp = await fetch(`${baseUrl}/manual/ejemplos?${query}`);
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron leer los ejemplos' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
