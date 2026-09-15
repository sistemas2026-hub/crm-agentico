import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Lista las propuestas de herramienta -- ver nucleo/canales/api.py:
 * GET /configuracion/propuestas. Mismo gate de ADMIN que el resto de esta
 * seccion (ver +server.js del chat, un nivel arriba).
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede ver esto.' }, { status: 403 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const estado = url.searchParams.get('estado');
  const query = new URLSearchParams({ tenant });
  if (estado) query.set('estado', estado);

  try {
    const resp = await fetch(`${baseUrl}/configuracion/propuestas?${query}`, { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron leer las propuestas' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
