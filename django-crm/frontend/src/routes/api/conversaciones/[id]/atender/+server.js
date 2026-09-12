import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { getTicketFormOptions, updateTicket } from '$lib/server/v2/tickets.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy para marcar una conversacion escalada como atendida sin pasar por
 * el chat -- el colaborador la resolvio por telefono, en persona, o por
 * otro canal. Ver nucleo/canales/api.py: POST /conversaciones/<id>/atender.
 *
 * Ademas toma el ticket: quien le da "Atender" a una conversacion escalada
 * queda como 'assigned_to' del caso en BottleCRM, para que "Asignado a" no
 * se quede en "Sin asignar" mientras alguien ya se hizo cargo. Es
 * best-effort -- si no hay ticket todavia, o la asignacion falla, 'atender'
 * ya se guardo igual y no se pierde por esto.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch, cookies, request }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json().catch(() => ({}));
  const casoId = cuerpo?.caso_id;

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/atender`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // 'por' sale de la sesion, nunca del cuerpo que manda el navegador.
      body: JSON.stringify({ tenant, por: locals.user.email })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo guardar' }, { status: resp.status });
    }

    let asignado = null;
    if (casoId) {
      try {
        const { owners } = await getTicketFormOptions({ cookies });
        const propio = owners.find(
          (/** @type {any} */ o) => o.name?.toLowerCase() === locals.user.email?.toLowerCase()
        );
        if (propio) {
          await updateTicket({ cookies }, casoId, { assigned_to: propio.id });
          asignado = propio;
        }
      } catch (/** @type {any} */ err) {
        console.error('[atender] no se pudo asignar el ticket:', err);
      }
    }

    return json({ ...datos, asignado });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
