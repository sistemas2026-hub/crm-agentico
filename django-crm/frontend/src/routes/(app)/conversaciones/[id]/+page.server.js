import { error, fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { getTicket, getTicketFormOptions, updateTicket } from '$lib/server/v2/tickets.js';
import { readableError } from '$lib/server/v2/form-errors.js';

/**
 * Server load: el hilo de una conversacion puntual, mas -- si ya se escalo
 * a un humano (nucleo/seguimiento/escalamiento.py le puso un caso_id) -- el
 * ticket real de BottleCRM que le corresponde, para mostrar y editar quien
 * lo tiene asignado sin reconstruir esa pantalla acá: getTicket/
 * getTicketFormOptions/updateTicket son las mismas funciones que ya usa
 * /tickets/[id]/edit.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch, cookies, params }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    error(500, 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)');
  }

  const resp = await fetch(
    `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/mensajes?tenant=${encodeURIComponent(tenant)}`
  );
  const datos = await resp.json();
  if (resp.status === 404) {
    error(404, 'Esta conversación no existe.');
  }
  if (!resp.ok) {
    error(500, datos.error || 'No se pudo cargar la conversación.');
  }

  let caso = null;
  let owners = [];
  if (datos.conversacion?.caso_id) {
    try {
      const [detalleCaso, opciones] = await Promise.all([
        getTicket({ cookies }, datos.conversacion.caso_id),
        getTicketFormOptions({ cookies })
      ]);
      caso = detalleCaso.ticket;
      owners = opciones.owners;
    } catch {
      // El chat sigue siendo util aunque el CRM este caido -- no se cae la
      // pagina entera por esto, mismo criterio que ya usa agentes/+page.server.js.
    }
  }

  return { conversacion: datos.conversacion, mensajes: datos.mensajes, caso, owners };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /** Cambia el responsable del ticket vinculado. Ver el mismo patron (un
   * solo valor, se empaqueta al M2M que pide la API) en tickets/[id]/edit. */
  asignar: async ({ cookies, request }) => {
    const form = await request.formData();
    const casoId = form.get('caso_id')?.toString() ?? '';
    const asignadoA = form.get('assigned_to')?.toString() ?? '';
    if (!casoId) return fail(400, { error: 'No hay ticket vinculado todavía.' });

    try {
      await updateTicket({ cookies }, casoId, { assigned_to: asignadoA });
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo asignar el ticket.') });
    }
    return { asignado: true };
  }
};
