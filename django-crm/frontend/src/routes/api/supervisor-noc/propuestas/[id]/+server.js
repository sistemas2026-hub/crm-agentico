import { json } from '@sveltejs/kit';
import { leerPropuesta } from '$lib/server/v2/supervisor-noc.js';

/**
 * El detalle de una propuesta, para el panel lateral.
 *
 * POR QUE EXISTE ESTA RUTA
 * ------------------------
 * El detalle se abria antes navegando con `?propuesta=<id>`, lo que recargaba
 * la pagina entera -- las 92 propuestas, los indicadores y el estado del motor
 * incluidos -- para mostrar una ficha. Aca se pide solo la ficha, y el panel
 * puede mostrar su propio "cargando" mientras llega.
 *
 * NO ES UN PROXY ABIERTO. Solo sabe pedir UN detalle de propuesta, por id, y
 * lo unico que hace con el es devolverlo. El JWT del colaborador viaja en la
 * cookie, asi que el 403 de 'EsJefeDeOperaciones' y el 404 de otra
 * organizacion siguen decidiendolos el backend, no esta capa.
 *
 * El gate de rol se repite aca ademas del que aplica el backend, por el mismo
 * motivo que en el resto del CRM: dos capas. Una ruta que solo dependiera de
 * que el boton este oculto no seria una barrera.
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
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver las propuestas.' },
      { status: 403 }
    );
  }

  const { datos, error } = await leerPropuesta({ cookies }, params.id);
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}
