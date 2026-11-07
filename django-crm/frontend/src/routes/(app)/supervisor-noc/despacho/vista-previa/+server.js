import { json } from '@sveltejs/kit';
import { leerVistaPreviaDeLasOrdenes } from '$lib/server/v2/despacho.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/**
 * Qué órdenes crearía el Supervisor ahora, sin crear nada (23/10/2026).
 *
 * Fase 2.3 de supervisor-arma-la-jornada: antes de que el Supervisor cree
 * órdenes solo, una persona ve qué crearía y por qué no las otras. NO ES UN
 * PROXY ABIERTO: pide una sola cosa. El rol se repite acá, como en el resto de
 * las rutas del Supervisor; el backend lo exige igual.
 */

/** El mismo conjunto que operaciones/permissions.py::EsJefeDeOperaciones. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede ver esto.' }, { status: 403 });
  }
  try {
    return json(await leerVistaPreviaDeLasOrdenes({ cookies }));
  } catch (e) {
    return json({ error: mensajeDeError(e) }, { status: /** @type {any} */ (e)?.status ?? 502 });
  }
}
