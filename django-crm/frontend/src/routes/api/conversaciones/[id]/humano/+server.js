import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Proxy para que un agente humano responda directo en una conversacion ya
 * escalada -- a diferencia de /api/conversaciones/[id] (que simula al
 * cliente y le contesta el bot), esto NUNCA pasa por el modelo: guarda tal
 * cual lo que el agente tipeo. Ver nucleo/canales/api.py:
 * POST /conversaciones/<id>/mensajes.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { mensaje } = await request.json();
  if (!mensaje) {
    return json({ error: 'Falta el mensaje' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/mensajes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenant, mensaje })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo guardar la respuesta' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
