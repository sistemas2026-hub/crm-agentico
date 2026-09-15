import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Nota interna: queda en el hilo para el equipo y NO se le envía al cliente.
 * Ver nucleo/canales/api.py: POST /conversaciones/<id>/nota.
 *
 * Ruta aparte de la que responde, a propósito. La garantía de que una nota no
 * salga al cliente no es una bandera dentro de un cuerpo JSON que alguien
 * puede armar mal: es que este camino no toca el canal en ningún punto.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch, request }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json(
      { error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 }
    );
  }

  const cuerpo = await request.json().catch(() => ({}));
  const mensaje = (cuerpo?.mensaje ?? '').trim();
  if (!mensaje) {
    return json({ error: 'La nota está vacía.' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/nota`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // El autor sale de la sesión: una nota firmada por quien dice el
      // navegador no sirve para nada.
      body: JSON.stringify({ tenant, mensaje, autor: locals.user.email ?? '' })
    });
    const datos = await resp.json();
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
