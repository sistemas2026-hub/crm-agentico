import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy hacia el motor del asistente, mismo patron que /api/asistente, pero
 * simulando un remitente de WhatsApp: la identidad no sale de la sesion
 * logueada (locals.user) sino del numero de telefono que ingresa quien
 * prueba -- eso es justamente lo que hay que poder variar para probar
 * distintos clientes. Sigue exigiendo estar logueado en BottleCRM: es una
 * herramienta de prueba para el equipo, no un endpoint publico.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { telefono, mensaje } = await request.json();
  if (!telefono || !mensaje) {
    return json({ error: 'Falta telefono o mensaje' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        rol: 'cliente_final',
        identificador_sesion: telefono,
        mensaje,
        // Canal propio para que el simulador nunca se confunda con trafico
        // real de WhatsApp una vez que ese canal exista de verdad.
        canal: 'whatsapp-simulado'
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'El asistente no respondio' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
