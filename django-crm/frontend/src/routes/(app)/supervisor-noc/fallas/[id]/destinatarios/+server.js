import { json } from '@sveltejs/kit';
import { leerDestinatarios } from '$lib/server/v2/fallas-de-red.js';
import { textoDelError } from '$lib/supervisor/fallas.js';

/**
 * A quién le llega el aviso de una caída (22/11/2026, rediseño del Supervisor).
 *
 * Lo pide el panel al abrirse, no el `load`: la lista de fallas sigue sin
 * traer los servicios (operaciones/tests/test_aviso_de_caida.py::test_e), y
 * esto sale solo cuando alguien lo pide. El backend decide qué se ve; acá no
 * se agrega ni se quita nada.
 */

/** El mismo conjunto que operaciones/permissions.py::EsJefeDeOperaciones. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, locals, cookies }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede ver esto.' }, { status: 403 });
  }
  if (!UUID.test(params.id)) return json({ error: 'Esa caída no se reconoce.' }, { status: 400 });
  try {
    const r = await leerDestinatarios({ cookies }, params.id);
    return json(r, { headers: { 'cache-control': 'no-store' } });
  } catch (/** @type {any} */ e) {
    const status = Number(e?.status) || 502;
    return json({ error: textoDelError(e?.body?.error ?? e?.error ?? null) }, { status });
  }
}
