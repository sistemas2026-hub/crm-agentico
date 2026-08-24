import { fail } from '@sveltejs/kit';
import { getTicket, replyToTicket, updateTicket } from '$lib/server/v2/tickets.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { leerResumenDelAgente } from '$lib/server/v2/resumen-agente.js';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, params, fetch }) {
  const datos = await getTicket({ cookies }, params.id);

  // El area del caso, para el panel lateral. Misma derivacion que la cola: el
  // CRM no tiene campo de area, la tiene el asistente y es por persona.
  let area = null;
  try {
    const base = env.PRIVATE_ASISTENTE_URL;
    const tenant = env.PRIVATE_ASISTENTE_TENANT;
    const responsable = datos.ticket?.assignee_id;
    if (base && tenant && responsable) {
      const r = await fetch(
        `${base}/agentes/asignaciones?tenant=${encodeURIComponent(tenant)}`,
        { headers: headersMotor() }
      );
      if (r.ok) {
        const d = await r.json();
        const nombre = (d.areas_por_persona ?? {})[responsable];
        area = (d.areas ?? []).find((/** @type {any} */ a) => a.nombre === nombre) ?? null;
      }
    }
  } catch {
    area = null;
  }

  // De donde vino el caso. El CRM no lo guarda: para el, un caso escalado es
  // un caso mas. El asistente si lo sabe, porque es la misma fila que marco
  // al escalar. Null para un ticket cargado a mano, que no tiene conversacion
  // detras -- y entonces la tarjeta no se dibuja, en vez de mostrar renglones
  // vacios o un origen inventado.
  let origen = null;
  try {
    const base = env.PRIVATE_ASISTENTE_URL;
    const tenant = env.PRIVATE_ASISTENTE_TENANT;
    if (base && tenant) {
      const r = await fetch(
        `${base}/conversaciones/por-caso/${params.id}?tenant=${encodeURIComponent(tenant)}`,
        { headers: headersMotor() }
      );
      if (r.ok) origen = (await r.json()).conversacion ?? null;
    }
  } catch {
    origen = null;
  }

  return {
    ...datos,
    area,
    origen,
    // Null cuando el caso no lo escribio el asistente (uno cargado a mano, o
    // uno viejo con otro formato): la pantalla vuelve entonces a mostrar la
    // descripcion tal cual, sin tarjetas a medio llenar.
    agente: leerResumenDelAgente(datos.ticket?.description ?? '')
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Post a reply, or an internal note.
   *
   * A reply may also move the ticket; "answer and set to Pending" is one
   * decision, not two, so the status change goes with it when the composer
   * asked for one. The reply is posted first: if the status change is refused
   * (the close gate, say) the customer has still been answered, which is the
   * order that loses the least.
   */
  reply: async ({ cookies, params, request }) => {
    const form = await request.formData();
    const body = form.get('body')?.toString().trim() ?? '';
    const internal = form.get('internal') === 'on';
    const status = form.get('status')?.toString().trim() ?? '';

    const picked = form.get('attachment');
    const file =
      picked && typeof picked === 'object' && 'size' in picked && picked.size > 0 ? picked : null;

    // A ticket accepts a file on its own, the API saves the attachment in a
    // block separate from the comment, so this refuses only the empty case.
    if (!body && !file) {
      return fail(400, {
        body,
        internal,
        error: 'Escribí algo o adjuntá un archivo antes de enviar.'
      });
    }

    try {
      await replyToTicket({ cookies }, params.id, { body, internal, file });
    } catch (/** @type {any} */ err) {
      return fail(400, { body, internal, error: readableError(err, 'No se pudo publicar esta respuesta.') });
    }

    if (status) {
      try {
        await updateTicket({ cookies }, params.id, { status });
      } catch (/** @type {any} */ err) {
        return fail(400, {
          sent: true,
          error: readableError(err, `Se publicó la respuesta, pero el estado no cambió.`)
        });
      }
    }

    return { sent: true, internal };
  },

  /**
   * Move the ticket without saying anything.
   *
   * Closing needs a date; `Case.clean()` has always said so and the serializer
   * now enforces it, so the button supplies today rather than bouncing the
   * user into a form to type a date they were never going to change. Where an
   * approval rule covers the ticket, the API refuses and says which rule.
   */
  setStatus: async ({ cookies, params, request }) => {
    const form = await request.formData();
    const status = form.get('status')?.toString().trim() ?? '';
    if (!status) return fail(400, { error: 'No se eligió ningún estado.' });

    /** @type {Record<string, any>} */
    const values = { status };
    if (status === 'Closed') values.closed_on = new Date().toISOString().slice(0, 10);

    try {
      await updateTicket({ cookies }, params.id, values);
    } catch (/** @type {any} */ err) {
      return fail(400, { error: readableError(err, 'No se pudo cambiar el estado.') });
    }

    return { moved: status };
  }
};
