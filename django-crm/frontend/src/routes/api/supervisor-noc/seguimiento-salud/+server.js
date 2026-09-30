import { json } from '@sveltejs/kit';
import { leerSaludDelSeguimiento } from '$lib/server/v2/programacion-noc.js';

/**
 * La salud del seguimiento de la jornada, para la bandeja.
 *
 * El veredicto lo calcula el backend y acá no se toca. La diferencia entre
 * «seguimiento vencido» y «sin sincronización reciente» es la diferencia entre
 * acusar a alguien de no reportar y admitir que no se sabe si tiene señal: no es
 * un detalle de presentación que un frontend pueda reinterpretar.
 *
 * El gate de rol se repite acá además del que aplica el backend: dos capas, igual
 * que el resto del CRM.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json(
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver el seguimiento.' },
      { status: 403 }
    );
  }

  const { datos, error } = await leerSaludDelSeguimiento({ cookies });
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
