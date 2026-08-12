import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Lista de documentos del corpus (solo lectura) -- proxy hacia
 * nucleo/canales/api.py:GET /corpus/documentos.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/corpus/documentos?tenant=${encodeURIComponent(tenant)}`);
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron leer los documentos' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
