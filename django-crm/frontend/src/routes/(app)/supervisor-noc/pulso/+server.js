import { json } from '@sveltejs/kit';
import { leerPulso } from '$lib/server/v2/pulso-noc.js';

/**
 * El Pulso del NOC (21/11/2026): las seis cifras de la franja que se ve en
 * todas las subpantallas del Supervisor. Ver lib/server/v2/pulso-noc.js.
 *
 * Lo pide el navegador DESPUÉS de dibujar la pantalla, y no el `load`: así
 * la franja nunca demora una subpantalla, y si el backend tarda, la pantalla
 * se ve igual y la franja dice «cargando».
 */

/** El mismo conjunto que operaciones/permissions.py::EsJefeDeOperaciones. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET(event) {
  const { locals } = event;
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede ver esto.' }, { status: 403 });
  }
  return json(await leerPulso(event), { headers: { 'cache-control': 'no-store' } });
}
