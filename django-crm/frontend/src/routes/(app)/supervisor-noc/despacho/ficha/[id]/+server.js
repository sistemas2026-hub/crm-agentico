import { json } from '@sveltejs/kit';
import { leerFichaDespachable } from '$lib/server/v2/despacho.js';

/**
 * La ficha de UN caso para despacharlo: barrio, lectura del Supervisor y
 * descripción del ticket tapada (13/10/2026).
 *
 * NO ES UN PROXY ABIERTO: pide una sola cosa, por id, y la devuelve. El JWT
 * del colaborador viaja en la cookie, así que el 404 de un caso no aprobado o
 * de otra empresa lo decide el backend. El rol se repite acá, como en el resto
 * de las rutas del Supervisor: una barrera que dependiera de un botón oculto
 * no sería una barrera.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede despachar.' }, { status: 403 });
  }
  const ficha = await leerFichaDespachable({ cookies }, params.id);
  if (!ficha) {
    return json({ error: 'No se pudo traer la ficha de este caso.' }, { status: 502 });
  }
  return json(ficha);
}
