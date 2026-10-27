import { fail, redirect } from '@sveltejs/kit';
import { createTicket, getTicketFormOptions } from '$lib/server/v2/tickets.js';
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
    const eco = { ...values, en_wisphub: enWispHub, servicio: wisphub.servicio };

    if (!values.name) {
      return fail(400, { values: eco, error: 'Un ticket necesita un asunto.' });
    }
    if (enWispHub) {
      if (!/^\d{1,12}$/.test(wisphub.servicio)) {
        return fail(400, { values: eco, error: 'El número de servicio de WispHub va solo con dígitos.' });
      }
      const habilitados = await leerAsuntosWispHub(locals, fetch);
      if (!habilitados.length) {
        return fail(400, {
          values: eco,
          error: 'No se pudo hablar con WispHub ahora. Desmarcá la casilla para crearlo solo en Dexter.'
        });
      }
      if (!habilitados.some((/** @type {any} */ a) => a.asunto === wisphub.asunto)) {
        return fail(400, { values: eco, error: 'Elegí el asunto de la lista de WispHub.' });
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
    //  con WispHub se va al ticket, y la pantalla del ticket dice el resultado.
    if (!enWispHub) redirect(303, `/tickets/${created.id}`);
    const r = /** @type {any} */ (await crearEnWispHub(locals, fetch, created.id, {
      servicio: wisphub.servicio,
      asunto: wisphub.asunto,
      descripcion: values.description
    }));
    const p = new URLSearchParams();
    if (r.ok) {
      p.set('wisphub', r.idTicket);
      if (!r.vinculado) p.set('wisphub_sin_atar', '1');
    } else {
      p.set('wisphub_error', r.motivo);
    }
    redirect(303, `/tickets/${created.id}?${p}`);
  }
};
