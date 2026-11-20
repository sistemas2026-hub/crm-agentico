import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

const ES_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * «Reproducir en el simulador» (12/11/2026): lo que escribió el cliente en una
 * conversación, solo texto, en orden y redactado por patrón. Proxy hacia
 * nucleo/canales/api.py:GET /simulador/reproduccion.
 *
 * La pantalla del simulador lo reenvía, mensaje por mensaje, a una
 * conversación NUEVA con canal simulado y un identificador que no es un
 * teléfono: se ve qué haría Dexter hoy con la misma conversación, sin tocar
 * al cliente ni la conversación original.
 *
 * ADMIN: trae lo que escribió un cliente real (aunque redactado), y sirve
 * para verificar una habilidad o un caso antes de aprobarlo, que también es
 * de ADMIN.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede reproducir una conversación.' },
      { status: 403 });
  }
  const conversacion = url.searchParams.get('conversacion') ?? '';
  if (!ES_UUID.test(conversacion)) {
    return json({ error: 'Conversación inválida.' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado' }, { status: 500 });
  }

  try {
    const qs = new URLSearchParams({ tenant, conversacion_id: conversacion });
    const resp = await fetch(`${baseUrl}/simulador/reproduccion?${qs}`, {
      headers: headersMotor(),
      signal: AbortSignal.timeout(8000)
    });
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer la conversación.' },
        { status: resp.status });
    }
    return json({ mensajes: datos.mensajes ?? [] });
  } catch (/** @type {any} */ err) {
    console.error('[simulador] reproduccion: motor inalcanzable:', err?.name ?? 'error');
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
