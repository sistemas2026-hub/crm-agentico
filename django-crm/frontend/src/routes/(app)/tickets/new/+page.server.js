import { fail, redirect } from '@sveltejs/kit';
import { createTicket, getTicketFormOptions, replyToTicket } from '$lib/server/v2/tickets.js';

//  El mismo tope que el CRM (common/utils.py, ATTACHMENT_MAX_BYTES): pasado
//  eso el archivo se rechaza ANTES de crear el ticket, no despues.
const ADJUNTO_MAX_BYTES = 25 * 1024 * 1024;
import { readableError } from '$lib/server/v2/form-errors.js';
import { leerAsuntosWispHub, crearEnWispHub } from '$lib/server/v2/ticket-desde-dexter.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, url, locals, fetch }) {
  const [opciones, asuntosWispHub] = await Promise.all([
    getTicketFormOptions({ cookies }, url.searchParams.get('account')),
    //  [] = la empresa no tiene asuntos habilitados, o el motor no contesto:
    //  el formulario no ofrece WispHub y el ticket se crea solo aca.
    leerAsuntosWispHub(locals, fetch)
  ]);
  return { ...opciones, asuntosWispHub };
}

/** @type {import('./$types').Actions} */
export const actions = {
  create: async ({ cookies, request, locals, fetch }) => {
    const form = await request.formData();

    /** @type {Record<string, any>} */
    const values = {};
    for (const field of ['name', 'status', 'priority', 'case_type', 'description', 'account']) {
      values[field] = form.get(field)?.toString().trim() ?? '';
    }

    const owner = form.get('assigned_to')?.toString().trim() ?? '';
    if (owner) values.assigned_to = owner;
    const contacts = form.getAll('contacts').map((id) => id.toString());
    if (contacts.length) values.contacts = contacts;

    //  TAMBIEN EN WISPHUB  --  26/10/2026. Se valida antes de crear nada, para
    //  no dejar un caso a medias por un numero mal tipeado. Que el servicio
    //  exista lo decide el motor.
    //
    //  27/10/2026: con la casilla marcada el asunto del ticket ES el de
    //  WispHub -- un solo campo, elegido de la lista, como llegan los tickets
    //  importados. Un asunto fuera de la lista no crea el caso: el motor lo
    //  rechazaria DESPUES de creado.
    const enWispHub = form.get('en_wisphub') === '1';
    const wisphub = {
      servicio: form.get('servicio')?.toString().trim() ?? '',
      asunto: values.name
    };
    //  'cliente_nombre' solo vuelve a la pantalla si algo falla, para que el
    //  cliente elegido siga a la vista: el motor no lo usa.
    const eco = {
      ...values,
      en_wisphub: enWispHub,
      servicio: wisphub.servicio,
      cliente_nombre: form.get('cliente_nombre')?.toString().trim() ?? ''
    };

    const elegido = form.get('attachment');
    const adjunto =
      elegido && typeof elegido === 'object' && 'size' in elegido && elegido.size > 0 ? elegido : null;

    if (!values.name) {
      return fail(400, { values: eco, error: 'Un ticket necesita un asunto.' });
    }
    if (adjunto && adjunto.size > ADJUNTO_MAX_BYTES) {
      return fail(400, { values: eco, error: 'El archivo pesa más de 25 MB. Elegí uno más liviano.' });
    }
    //  El asunto sale de la lista de WispHub CON la casilla o SIN ella
    //  (decision del usuario, 27/10/2026: que Dexter no tenga asuntos
    //  distintos a los del ISP). Sin lista -- la empresa no la habilito o el
    //  motor no contesto -- solo se puede crear aca, con texto libre.
    const habilitados = await leerAsuntosWispHub(locals, fetch);
    if (enWispHub && !habilitados.length) {
      return fail(400, {
        values: eco,
        error: 'No se pudo hablar con WispHub ahora. Desmarcá la casilla para crearlo solo en Dexter.'
      });
    }
    if (habilitados.length && !habilitados.some((/** @type {any} */ a) => a.asunto === values.name)) {
      return fail(400, { values: eco, error: 'Elegí el asunto de la lista de WispHub.' });
    }
    if (enWispHub) {
      if (!wisphub.servicio) {
        return fail(400, { values: eco, error: 'Buscá y elegí el cliente antes de crearlo en WispHub.' });
      }
      if (!/^\d{1,12}$/.test(wisphub.servicio)) {
        return fail(400, { values: eco, error: 'El número de servicio de WispHub va solo con dígitos.' });
      }
      if (!values.description) {
        return fail(400, { values: eco, error: 'Para crearlo en WispHub hace falta contar qué pasó.' });
      }
    }

    /** @type {any} */
    let created;
    try {
      created = await createTicket({ cookies }, values);
    } catch (/** @type {any} */ err) {
      return fail(400, { values: eco, error: readableError(err, 'No se pudo crear este ticket.') });
    }
    if (!created?.id) redirect(303, '/tickets');

    //  El caso YA existe (guardar primero, entregar despues). Pase lo que pase
    //  con el adjunto o con WispHub se va al ticket, y la pantalla del ticket
    //  dice el resultado.
    const p = new URLSearchParams();

    //  ADJUNTO  --  27/10/2026. Se sube al caso ya creado, por el mismo camino
    //  que el adjunto de una respuesta (CaseDetailView.post lo guarda aparte
    //  del comentario: sin texto no hay comentario, ni primera respuesta).
    //  Con la casilla, ademas viaja al ticket de WispHub (abajo).
    if (adjunto) {
      try {
        await replyToTicket({ cookies }, created.id, { body: '', file: adjunto });
      } catch (/** @type {any} */ err) {
        p.set('adjunto_error', readableError(err, 'No se pudo subir el archivo.'));
      }
    }

    if (enWispHub) {
      //  El archivo tambien va al ticket de WispHub (decision del usuario,
      //  27/10/2026). En base64 porque el puente con el motor es JSON, como
      //  la orden de instalacion (solicitudes/entrega.py).
      const archivo = adjunto
        ? {
            nombre: adjunto.name,
            tipo: adjunto.type || 'application/octet-stream',
            base64: Buffer.from(await adjunto.arrayBuffer()).toString('base64')
          }
        : undefined;
      const r = /** @type {any} */ (await crearEnWispHub(locals, fetch, created.id, {
        servicio: wisphub.servicio,
        asunto: wisphub.asunto,
        descripcion: values.description,
        ...(archivo ? { archivo } : {})
      }));
      if (r.ok) {
        p.set('wisphub', r.idTicket);
        if (!r.vinculado) p.set('wisphub_sin_atar', '1');
        if (r.adjunto === false) p.set('wisphub_sin_adjunto', '1');
      } else {
        p.set('wisphub_error', r.motivo);
      }
    }
    const q = p.toString();
    redirect(303, `/tickets/${created.id}${q ? `?${q}` : ''}`);
  }
};
