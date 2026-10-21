import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Las conversaciones ANTERIORES del chat de este número (21/10/2026,
 * contrato §4.5). La primera página la trae el load de la conversación; esto
 * es "Ver conversaciones anteriores".
 *
 * Por id y nunca por teléfono: la URL termina en los logs de acceso. El
 * número lo resuelve el motor desde el id, dentro de la empresa de la sesión.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ params, url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ tramos: [], hay_anteriores: false, antes: null }, { status: 503 });
  }
  const q = new URLSearchParams({ tenant });
  const antes = url.searchParams.get('antes');
  if (antes) q.set('antes', antes);
  // El sondeo de un chat cerrado pide una sola: solo quiere el mapa del chat.
  const limite = url.searchParams.get('limite');
  if (limite && /^[1-5]$/.test(limite)) q.set('limite', limite);
  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/hilo?${q}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(8000) }
    );
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer el chat.' }, { status: resp.status });
    }
    return json(datos);
  } catch {
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
