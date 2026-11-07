import { json } from '@sveltejs/kit';
import { buscarClientes } from '$lib/server/v2/ticket-desde-dexter.js';

/**
 * POST { q: <servicio, cédula o nombre> } -> { ok, resultados, mas, cargando } | { ok: false, motivo }
 *
 * Lo usa "Buscar" de Nuevo ticket (28/10/2026; antes "Verificar", que pedía
 * el número de servicio y nada más). De cada cliente llega servicio, nombre y
 * estado -- nada más de la ficha sale del motor.
 *
 * POST y no GET (revisor-de-pii, 28/10/2026): lo buscado es la cédula o el
 * nombre de una persona, y en la URL quedaría en cualquier registro de acceso
 * del camino público (el proxy de entrada lo guarda entero si lo tiene
 * encendido). En el cuerpo no queda en ninguno.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  const cuerpo = await request.json().catch(() => ({}));
  return json(await buscarClientes(locals, fetch, typeof cuerpo?.q === 'string' ? cuerpo.q : ''));
}
