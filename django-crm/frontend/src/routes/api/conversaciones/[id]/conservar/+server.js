import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy para sacar (o volver a meter) una conversacion en la purga por
 * retencion. Ver nucleo/canales/api.py: POST /conversaciones/<id>/conservar.
 *
 * NO es lo mismo que marcar un ejemplo (/mensajes/[mensajeId]/marcar): un
 * ejemplo dice "esta respuesta fue buena" y alimenta el manual; esto dice "no
 * la borres todavia", que es lo que hace falta con un reclamo o un incidente
 * -- justo lo que NO hay que copiar como ejemplo.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { conservar, motivo } = await request.json();

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/conservar`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // 'por' sale de la sesion, nunca del cuerpo que manda el navegador: es
      // quien tomo la decision, y no puede ser un valor que el cliente elija.
      body: JSON.stringify({ tenant, conservar, motivo, por: locals.user.email })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo guardar' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
