import { redirect } from '@sveltejs/kit';
import { leerTableroCapacidad, PERIODOS } from '$lib/server/v2/capacidad.js';

/**
 * Capacidad: cuánto trabajo le resolvió Dexter a la empresa (PRD §2).
 *
 * Solo ADMIN, como Consumo: son cifras de negocio de la empresa, no de la
 * operación de un colaborador.
 *
 * Se pasa la respuesta del motor ENTERA y sin renombrar: la pantalla lee las
 * mismas claves que escribe nucleo/observabilidad/capacidad.py. Una capa que
 * traduce nombres es donde se pierde un dato con el backend en verde
 * (CLAUDE.md §6, `requiere_noc`).
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch, url }) {
  if (locals.profile?.role !== 'ADMIN') {
    redirect(303, '/');
  }
  const pedido = Number(url.searchParams.get('dias'));
  const dias = PERIODOS.includes(pedido) ? pedido : 30;
  const { tablero, error } = await leerTableroCapacidad(locals, fetch, dias);
  return { tablero, dias, periodos: PERIODOS, error };
}
