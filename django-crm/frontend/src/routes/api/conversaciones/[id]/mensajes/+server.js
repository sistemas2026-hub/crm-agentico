import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Proxy de solo lectura para sondear mensajes nuevos sin recargar la
 * pagina -- usado por [id]/+page.svelte mientras la conversacion esta
 * abierta, para que un mensaje entrante (WhatsApp real, cuando este
 * integrado) aparezca solo. Distinto del load() de la pantalla: ese trae
 * ademas el ticket de BottleCRM, las herramientas y los casos del manual,
 * pesado para pedirlo cada pocos segundos. Este solo trae mensajes.
 *
 * Ver nucleo/canales/api.py: GET /conversaciones/<id>/mensajes.
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
      `${baseUrl}/conversaciones/${params.id}/mensajes?tenant=${encodeURIComponent(tenant)}`
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer la conversacion' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
