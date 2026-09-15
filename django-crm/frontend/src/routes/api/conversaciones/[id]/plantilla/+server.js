import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Enviar una plantilla aprobada de WhatsApp.
 * Ver nucleo/canales/api.py: POST /conversaciones/<id>/plantilla.
 *
 * Ruta aparte de la que responde texto, igual que las notas: son dos cosas
 * distintas del lado de Meta —una la rechaza fuera de la ventana de 24 h y la
 * otra no— y mezclarlas en un mismo endpoint con una bandera obligaría a que
 * el cuerpo JSON fuera la garantía.
 *
 * El motor vuelve a validar el nombre contra las plantillas aprobadas: lo que
 * llegue de acá es una intención, no un permiso.
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
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const cuerpo = await request.json().catch(() => ({}));
  const plantilla = (cuerpo?.plantilla ?? '').trim();
  if (!plantilla) {
    return json({ error: 'Falta elegir una plantilla.' }, { status: 400 });
  }
  const variables = Array.isArray(cuerpo?.variables) ? cuerpo.variables : [];

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/plantilla`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // El autor sale de la sesión, no del navegador: una plantilla firmada
      // por quien diga el cliente HTTP no sirve para auditar nada.
      body: JSON.stringify({
        tenant,
        plantilla,
        variables,
        autor: locals.user.email ?? ''
      })
    });
    const datos = await resp.json();
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json(
      { error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 }
    );
  }
}
