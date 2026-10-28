import { leerDiaPublicado } from '$lib/server/v2/dia-publicado.js';
import { hoyDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';

/**
 * Programación — lo que quedó publicado un día (28/10/2026).
 *
 * Pedido del usuario: «cuando el supervisor publique, salga en Programación lo
 * que publicó», con esta pantalla después de Despacho. Despacho es lo que
 * FALTA; esto es lo que QUEDÓ: por cuadrilla, cada orden con quién la asignó
 * (el Supervisor o una persona) y a qué hora, y si al técnico le llegó el
 * aviso.
 *
 * La pantalla de antes —los planes semanales— vive en
 * /supervisor-noc/planes-semanales, enlazada desde acá.
 *
 * Solo lee. Solo quien gestiona: muestra el trabajo de todas las cuadrillas y
 * el nombre de cada técnico (el backend lo exige igual).
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies, locals }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
  if (!ROLES_GESTION.has(rol)) return { puedeVer: false, dia: '', publicado: null, error: false };

  //  Hoy en el reloj de la EMPRESA, no en el del servidor (UTC).
  const pedido = (url.searchParams.get('dia') ?? '').trim();
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(pedido) ? pedido : await hoyDeLaEmpresa(locals, cookies);
  const { publicado, error } = await leerDiaPublicado({ cookies }, dia);
  return { puedeVer: true, dia, publicado, error };
}
