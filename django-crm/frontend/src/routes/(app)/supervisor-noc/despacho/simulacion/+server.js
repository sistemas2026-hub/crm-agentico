import { json } from '@sveltejs/kit';
import { leerSimulacionDelDia } from '$lib/server/v2/despacho.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/**
 * Simular el día (24/10/2026): las cuadrillas, las órdenes y el reparto como
 * los dejaría el Supervisor, sin guardar nada.
 *
 * Pedido del usuario: ver cómo dejaría distribuidos los tickets a los técnicos,
 * con qué carga y si la labor cuadra, antes de dejarlo hacerlo de verdad. NO ES
 * UN PROXY ABIERTO: pide una sola cosa, por fecha. El rol se repite acá, como en
 * el resto de las rutas del Supervisor; el backend lo exige igual.
 */

/** El mismo conjunto que operaciones/permissions.py::EsJefeDeOperaciones. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ url, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede ver esto.' }, { status: 403 });
  }
  const fecha = url.searchParams.get('fecha') ?? '';
  try {
    return json(await leerSimulacionDelDia({ cookies }, fecha));
  } catch (e) {
    return json({ error: mensajeDeError(e) }, { status: /** @type {any} */ (e)?.status ?? 502 });
  }
}
