import { json } from '@sveltejs/kit';
import { leerBloqueosAbiertos } from '$lib/server/v2/programacion-noc.js';

/**
 * Los bloqueos vivos de la empresa, para los filtros de la bandeja.
 *
 * `?requiere_noc=1` devuelve solo los que le tocan al NOC. Son dos preguntas
 * distintas y las dos son verdad a la vez: un trabajo puede estar detenido
 * esperando al cliente —bloqueado, sí; cosa del NOC, no—. Ver campo/bloqueos.py.
 *
 * El gate de rol se repite acá además del que aplica el backend: dos capas, igual
 * que el resto del CRM.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ url, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json(
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver los bloqueos.' },
      { status: 403 }
    );
  }

  const soloNoc = url.searchParams.get('requiere_noc') === '1';
  const { datos, error } = await leerBloqueosAbiertos({ cookies }, { soloNoc });
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
