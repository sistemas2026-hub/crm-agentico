import { error } from '@sveltejs/kit';
import { leerFichaDelCliente } from '$lib/server/v2/hilo-del-cliente.js';

/**
 * LA FICHA DEL CLIENTE POR SU SERVICIO (12/11/2026, auditoría del menú §1
 * punto 2 y §4 ítem 5).
 *
 * No había un lugar donde ver a UN cliente entero: sus conversaciones, sus
 * tickets, sus visitas, sus solicitudes y cómo está su servicio. La clave es
 * el identificador del servicio en el ISP, el mismo que usan el motor y el
 * historial de visitas; nunca el nombre ni el teléfono.
 *
 * QUIÉN VE QUÉ lo decide cada backend con su regla: los tickets, los que la
 * persona puede abrir; las órdenes, las visibles; las solicitudes, solo la
 * gestión; la ficha de la persona, el criterio por área del motor. Esta capa
 * no filtra ni amplía nada.
 */

/** @type {import('./$types').PageServerLoad} */
export async function load({ params, cookies, locals, fetch }) {
  if (!locals.user) error(401, 'Tu sesión expiró. Volvé a iniciar sesión.');
  const { crm, motor, error: fallo } = await leerFichaDelCliente(
    { cookies, locals, fetch },
    params.id_servicio
  );
  if (fallo?.status === 404 && !crm) error(404, fallo.mensaje);
  return {
    servicio: params.id_servicio,
    tickets: crm?.tickets ?? null,
    ordenes: crm?.ordenes ?? null,
    solicitudes: crm?.solicitudes ?? null,
    errorCrm: fallo?.mensaje ?? null,
    conversaciones: motor?.conversaciones ?? null,
    contexto: motor?.contexto ?? null,
    // El motor no contestó: no es «no tiene conversaciones».
    motorSinRespuesta: motor === null
  };
}
