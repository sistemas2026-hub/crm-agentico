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

    //  TAMBIEN EN WISPHUB  --  26/10/2026. Se valida la FORMA antes de crear
    //  nada, para no dejar un caso a medias por un numero mal tipeado. Que el
    //  servicio exista y que el asunto este habilitado lo decide el motor.
    const enWispHub = form.get('en_wisphub') === '1';
    const wisphub = {
      servicio: form.get('servicio')?.toString().trim() ?? '',
      asunto: form.get('asunto_wisphub')?.toString().trim() ?? ''
    };
    const eco = { ...values, en_wisphub: enWispHub, ...wisphub };

    if (!values.name) {
      return fail(400, { values: eco, error: 'Un ticket necesita un asunto.' });
    }
    if (enWispHub) {
      if (!/^\d{1,12}$/.test(wisphub.servicio)) {
        return fail(400, { values: eco, error: 'El número de servicio de WispHub va solo con dígitos.' });
      }
      if (!wisphub.asunto) {
        return fail(400, { values: eco, error: 'Elegí con qué asunto se abre en WispHub.' });
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
      ...wisphub,
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
