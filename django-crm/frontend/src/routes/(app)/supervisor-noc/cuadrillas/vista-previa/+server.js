import { json } from '@sveltejs/kit';
import { leerVistaPreviaDeLaJornada } from '$lib/server/v2/cuadrillas.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/**
 * Lo que armaría el Supervisor ese día, sin escribir nada (21/10/2026).
 *
 * Pedido del usuario: ver ya lo que armaría, sin esperar al día siguiente.
 * NO ES UN PROXY ABIERTO: pide una sola cosa, por fecha. El rol se repite
 * acá, como en el resto de las rutas del Supervisor; el backend lo exige igual.
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
    return json(await leerVistaPreviaDeLaJornada({ cookies }, fecha));
  } catch (e) {
    return json({ error: mensajeDeError(e) }, { status: /** @type {any} */ (e)?.status ?? 502 });
  }
}
