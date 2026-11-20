/**
 * Guardar la instrucción probada en la plantilla.
 *
 * Hermano de `../probar-instruccion/`. La diferencia es que esto SÍ escribe:
 * publica una versión nueva de la plantilla (el backend la compone; acá solo
 * viaja el texto). Las órdenes vivas conservan la suya, y la respuesta trae el
 * conteo para poder decírselo a quien guarda.
 *
 * Dos capas de permiso, como el resto del Supervisor NOC: el backend decide
 * (gestión, el mismo gate que publicar una plantilla) y acá se repite.
 */

import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @type {import('./$types').RequestHandler} */
export async function POST({ params, cookies, locals, request }) {
  if (!locals.user) return new Response(null, { status: 401 });
  if (!ROLES_GESTION.has(locals.profile?.role)) return new Response(null, { status: 403 });
  if (!UUID_RE.test(params.id)) return new Response(null, { status: 404 });

  const accessToken = cookies.get('jwt_access');
  if (!accessToken) return new Response(null, { status: 401 });

  let cuerpo;
  try {
    cuerpo = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'CUERPO_INVALIDO' }), {
      status: 400,
      headers: { 'content-type': 'application/json' }
    });
  }

  const upstream = await fetch(
    `${API_BASE_URL}/campo/evidencias/${params.id}/guardar-instruccion/`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'content-type': 'application/json'
      },
      //  SOLO el campo que la ruta acepta.
      body: JSON.stringify({ instrucciones: cuerpo?.instrucciones ?? '' }),
      signal: request.signal
    }
  );

  const texto = await upstream.text();
  return new Response(texto, {
    status: upstream.status,
    headers: { 'content-type': 'application/json' }
  });
}
