import { json } from '@sveltejs/kit';
import { leerOrden } from '$lib/server/v2/programacion-noc.js';

/**
 * El detalle de una orden de trabajo, para el panel de programación.
 *
 * EL RECORTE DE DATOS DEL CLIENTE SE HACE EN EL SERVIDOR
 * -----------------------------------------------------
 * 'leerOrden' descarta teléfono y coordenadas GPS antes de devolver nada, así
 * que no viajan al navegador. Ocultarlos en la pantalla habría dejado los
 * datos en la respuesta, a un "ver código fuente" de distancia.
 *
 * El gate de rol se repite aquí además del que aplica el backend: dos capas,
 * igual que el resto del CRM.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json(
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver las órdenes.' },
      { status: 403 }
    );
  }

  const { datos, error } = await leerOrden({ cookies }, params.id);
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
