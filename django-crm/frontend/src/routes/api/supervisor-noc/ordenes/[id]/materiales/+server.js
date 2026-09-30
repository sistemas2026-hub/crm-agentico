import { json } from '@sveltejs/kit';
import { leerMaterialesDeOrden } from '$lib/server/v2/programacion-noc.js';

/**
 * Qué material tocó una orden: comprometido, consumido, devuelto y otros.
 *
 * Solo GET. Mover inventario entra por las rutas de inventario, que son las que
 * tienen la frontera de autorización puesta; una ruta de lectura que además
 * escribiera dejaría dos caminos hacia el mismo efecto y uno sin guardas.
 *
 * El gate de rol se repite aquí además del que aplica el backend: dos capas,
 * igual que el resto del CRM. El aislamiento por empresa lo garantiza el backend
 * con 404 estricto — nunca 403 — así que un UUID de otra empresa no se confirma.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, url, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json(
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver las órdenes.' },
      { status: 403 }
    );
  }

  // El kit del día solo si se pide: no es material de esta orden.
  const custodia = url.searchParams.get('custodia') === '1';
  const { datos, error } = await leerMaterialesDeOrden({ cookies }, params.id, { custodia });
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
