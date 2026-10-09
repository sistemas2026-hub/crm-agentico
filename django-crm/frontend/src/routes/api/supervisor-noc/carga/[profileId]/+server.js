import { json } from '@sveltejs/kit';
import { leerCargaPersona } from '$lib/server/v2/programacion-noc.js';

/**
 * La carga de una persona en un día, para el panel lateral.
 *
 * El día viaja como parámetro de consulta porque la capacidad no existe "en
 * general": se deriva para una fecha, y sin ella la pregunta no significa
 * nada — el mismo motivo por el que la jornada exige filtro.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, url, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json({ error: 'Solo el Jefe de Operaciones puede ver la carga del equipo.' }, { status: 403 });
  }

  const dia = url.searchParams.get('dia') ?? '';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dia)) {
    return json({ error: 'Falta el día de la jornada.' }, { status: 400 });
  }

  const { datos, error } = await leerCargaPersona({ cookies }, dia, params.profileId);
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
