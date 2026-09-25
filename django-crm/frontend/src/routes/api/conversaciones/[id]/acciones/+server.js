import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Las acciones de esta conversación, con su estado real (B5).
 * Ver nucleo/canales/api.py: GET /conversaciones/<id>/acciones.
 *
 * Sólo lectura. El motor no manda `argumentos` —los valores reales con los que
 * se iba a escribir afuera— y este proxy tampoco los pide.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch, params }) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/acciones` +
        `?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    );
    return json(await resp.json(), { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json(
      { error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 }
    );
  }
}
