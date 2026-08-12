import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * El texto vigente de un documento puntual, en orden -- proxy hacia
 * nucleo/canales/api.py:GET /corpus/documentos/<id>/fragmentos. Se pide al
 * abrir cada documento en /manual, no de entrada: un corpus puede tener
 * muchos fragmentos y no hace falta traerlos todos si nadie los mira.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ params, locals, fetch }) {
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
    const resp = await fetch(
      `${baseUrl}/corpus/documentos/${params.id}/fragmentos?tenant=${encodeURIComponent(tenant)}`
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron leer los fragmentos' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
