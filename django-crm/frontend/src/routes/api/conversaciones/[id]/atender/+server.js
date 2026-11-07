import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { getTicketFormOptions, updateTicket } from '$lib/server/v2/tickets.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

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
  const tenant = await tenantDeLaSesion(locals, fetch);
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
      // 'soltar' y la clave vienen de la pantalla; el autor, de la sesion.
      // Antes 'soltar' se perdia aca: el motor volvia a TOMAR la conversacion
      // y el boton "Soltar" no hacia nada (D22).
      body: JSON.stringify({
        tenant,
        ...autorDeSesion(locals),
        soltar: !!cuerpo?.soltar,
        clave_operacion: typeof cuerpo?.clave_operacion === 'string' ? cuerpo.clave_operacion : undefined
      })
    });
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      // El 409 viaja entero: 'codigo' y 'asignada_a' son lo que la pantalla
      // necesita para decir que paso (otra persona la tomo primero) en vez de
      // un error generico (B3.4).
      return json({ error: datos.error || 'No se pudo guardar', codigo: datos.codigo,
        asignada_a: datos.asignada_a }, { status: resp.status });
    }

    let asignado = null;
    // Solo al TOMAR y solo si de verdad se tomo ahora: al soltar, o si el
    // motor no cambio nada, asignarse el ticket seria mentirle al CRM.
    if (casoId && !cuerpo?.soltar && datos.aplicada) {
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
