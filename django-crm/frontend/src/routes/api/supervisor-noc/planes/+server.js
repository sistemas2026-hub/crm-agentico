import { json } from '@sveltejs/kit';
import { listarPlanes } from '$lib/server/v2/programacion-noc.js';

/**
 * Los planes semanales que admiten órdenes nuevas.
 *
 * Se pide desde el diálogo de programar, cuando se abre: cargarlos en el
 * `load` de la página los traería en cada visita para una acción que casi
 * nunca se usa.
 *
 * `admite_lineas` lo aplica el backend con la misma constante que el servicio
 * usa al programar. Esta ruta no filtra por su cuenta: reenvía el parámetro.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, locals, url }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede ver los planes semanales.' }, { status: 403 });
  }

  // Por defecto solo los que admiten líneas: ofrecer un plan cerrado sería
  // ofrecer una opción que el servicio rechaza después.
  const todos = url.searchParams.get('todos') === '1';
  const { count, planes, error } = await listarPlanes({ cookies }, !todos);

  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json({ count, planes });
}
