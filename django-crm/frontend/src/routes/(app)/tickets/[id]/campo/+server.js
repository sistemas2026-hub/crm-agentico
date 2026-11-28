import { json } from '@sveltejs/kit';
import { leerOrdenesDelCaso } from '$lib/server/v2/hilo-del-cliente.js';

/**
 * Las visitas de campo de este ticket, para el bloque «Campo» del carril
 * (12/11/2026).
 *
 * POR QUÉ UNA RUTA Y NO EL `load` DE LA PÁGINA: el `+page.server.js` del
 * ticket lo está cambiando otra entrega (la ficha por rol), y el bloque se
 * pide aparte para no pisarla. Además no demora la apertura del ticket: el
 * carril se completa cuando llega.
 *
 * El permiso lo decide el backend (quien puede abrir el ticket ve sus visitas;
 * el enlace a cada orden, solo quien puede abrirla). Acá solo se exige sesión.
 */

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  const { datos, error } = await leerOrdenesDelCaso({ cookies }, params.id);
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
