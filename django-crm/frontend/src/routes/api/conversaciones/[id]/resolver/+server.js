import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy para dar un caso por TERMINADO. Ver nucleo/canales/api.py:
 * POST /conversaciones/<id>/resolver.
 *
 * No es lo mismo que 'atender' (la ruta hermana), y confundirlas cambia lo
 * que le pasa al cliente:
 *
 *   atender   alguien esta en esto  -> sale de "Sin atender", el hilo sigue vivo
 *   resolver  esto ya termino       -> se cierra, y el proximo mensaje de esa
 *                                      persona empieza de cero
 *
 * Por eso 'atender' toma ademas el ticket del CRM y esta no: asignarse un
 * caso que se acaba de cerrar no le sirve a nadie.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch }) {
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

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/resolver`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // 'por' sale de la sesion, nunca del cuerpo que manda el navegador.
      body: JSON.stringify({ tenant, por: locals.user.email })
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
