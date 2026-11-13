import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

const ES_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * La traza de UN turno del simulador (12/11/2026): qué herramientas llamó el
 * agente, a qué área derivó y qué falló. Proxy hacia
 * nucleo/canales/api.py:GET /simulador/traza.
 *
 * Hasta hoy la pantalla mostraba la respuesta y nada más, aunque la traza se
 * persiste en cada turno: lo que hizo el agente había que ir a buscarlo a la
 * base. El motor solo la sirve para conversaciones que NO son de un canal
 * real (la de un cliente se mira en Conversaciones).
 *
 * La traza se escribe un instante DESPUÉS de la respuesta; `completa` dice si
 * ya está toda, y la pantalla vuelve a preguntar mientras sea false.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const conversacion = url.searchParams.get('conversacion') ?? '';
  const desde = url.searchParams.get('desde') ?? '';
  if (!ES_UUID.test(conversacion) || !ES_UUID.test(desde)) {
    return json({ error: 'Faltan la conversación o el turno.' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado' }, { status: 500 });
  }

  try {
    const qs = new URLSearchParams({ tenant, conversacion_id: conversacion, desde_mensaje: desde });
    const resp = await fetch(`${baseUrl}/simulador/traza?${qs}`, {
      headers: headersMotor(),
      signal: AbortSignal.timeout(8000)
    });
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer la traza.' }, { status: resp.status });
    }
    return json({
      completa: !!datos.completa,
      herramientas: datos.herramientas ?? [],
      derivo_a: datos.derivo_a ?? null,
      errores: datos.errores ?? []
    });
  } catch (/** @type {any} */ err) {
    console.error('[simulador] traza: motor inalcanzable:', err?.name ?? 'error');
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
