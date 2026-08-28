import { fail } from '@sveltejs/kit';
import { getTicket, replyToTicket, updateTicket } from '$lib/server/v2/tickets.js';
import { readableError } from '$lib/server/v2/form-errors.js';
import { leerResumenDelAgente } from '$lib/server/v2/resumen-agente.js';
import { leerAreas } from '$lib/server/v2/areas.js';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, params, fetch }) {
  const datos = await getTicket({ cookies }, params.id);

  // El area del caso, para el panel lateral. Misma derivacion que la cola: el
  // CRM no tiene campo de area, la tiene el asistente y es por persona.
  //
  // Se pide a '/agentes/areas', no a '/agentes/asignaciones': aquella sale
  // ademas al sistema externo a buscar candidatos, que esta pantalla no usa.
  let area = null;
  const responsable = datos.ticket?.assignee_id;
  if (responsable) {
    const { areas, areaPorPersona } = await leerAreas(fetch);
    const nombre = areaPorPersona[responsable];
    area = areas.find((/** @type {any} */ a) => a.nombre === nombre) ?? null;
  }

  // De donde vino el caso. El CRM no lo guarda: para el, un caso escalado es
  // un caso mas. El asistente si lo sabe, porque es la misma fila que marco
  // al escalar. Null para un ticket cargado a mano, que no tiene conversacion
  // detras -- y entonces la tarjeta no se dibuja, en vez de mostrar renglones
  // vacios o un origen inventado.
  //
  // Va SIN await: la promesa se devuelve tal cual y el navegador la recibe
  // cuando resuelve. Adentro hay tres consultas a sistemas externos (la ficha
  // del cliente y el estado del equipo), y esperarlas antes de contestar
  // dejaba el ticket sin abrirse varios segundos -- con la pantalla anterior
  // todavia puesta, o sea el clic pareciendo perdido. El caso, la
  // conversacion y la respuesta no dependen de esto: llegan primero y esto
  // completa las tarjetas tecnicas cuando llega.
  const origen = (async () => {
    try {
      const base = env.PRIVATE_ASISTENTE_URL;
      const tenant = env.PRIVATE_ASISTENTE_TENANT;
      if (!base || !tenant) return null;
      const r = await fetch(
        `${base}/conversaciones/por-caso/${params.id}?tenant=${encodeURIComponent(tenant)}`,
        { headers: headersMotor(), signal: AbortSignal.timeout(20000) }
      );
      return r.ok ? ((await r.json()).conversacion ?? null) : null;
    } catch {
      // Se traga a proposito: sin esto una promesa rechazada tumba la
      // pagina entera, y lo que hay en juego son dos tarjetas de contexto.
      return null;
    }
  })();

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
