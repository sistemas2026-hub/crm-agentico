import { json } from '@sveltejs/kit';
import { titularDelServicio } from '$lib/server/v2/ticket-desde-dexter.js';

/**
 * GET ?servicio=<id> -> { ok, nombre, estado } | { ok: false, motivo }
 *
 * Lo usa el boton "Verificar" de Nuevo ticket: quien lo llena confirma que
 * ese numero es el cliente correcto antes de abrir el ticket en WispHub. Solo
 * nombre y estado -- nada mas de la ficha sale del motor.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  return json(await titularDelServicio(locals, fetch, url.searchParams.get('servicio') ?? ''));
}
