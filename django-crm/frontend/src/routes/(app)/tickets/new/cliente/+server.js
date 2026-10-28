import { json } from '@sveltejs/kit';
import { buscarClientes } from '$lib/server/v2/ticket-desde-dexter.js';

/**
 * GET ?q=<servicio, cédula o nombre> -> { ok, resultados, mas, cargando } | { ok: false, motivo }
 *
 * Lo usa "Buscar" de Nuevo ticket (28/10/2026; antes "Verificar", que pedía
 * el número de servicio y nada más). De cada cliente llega servicio, nombre y
 * estado -- nada más de la ficha sale del motor.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch }) {
  return json(await buscarClientes(locals, fetch, url.searchParams.get('q') ?? ''));
}
