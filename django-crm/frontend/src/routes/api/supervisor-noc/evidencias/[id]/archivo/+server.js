/**
 * Una foto de campo, para mirarla en la bitácora.
 *
 * POR QUÉ EXISTE (15/10/2026)
 * ---------------------------
 * Hasta acá ninguna foto se podía abrir en producción: el backend emitía
 * `/media/<key>`, que Django solo sirve en modo desarrollo. Las fotos llegaban y
 * se guardaban, y nadie las veía.
 *
 * El binario pasa de largo, sin guardarse: el navegador no tiene el token del
 * backend (vive en una cookie del servidor), así que un `<img>` no puede pedirle
 * la foto directo. El permiso lo decide el backend —el de la orden: otra empresa
 * o un técnico no asignado reciben 404— y acá se repite el gate de rol, igual
 * que el resto del Supervisor NOC.
 */

import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, cookies, locals, request }) {
  if (!locals.user) return new Response(null, { status: 401 });
  if (!ROLES_GESTION.has(locals.profile?.role)) return new Response(null, { status: 403 });
  //  Lo que va en la URL del backend se valida antes: un id que no es UUID no
  //  puede convertirse en otra ruta.
  if (!UUID_RE.test(params.id)) return new Response(null, { status: 404 });

  const accessToken = cookies.get('jwt_access');
  if (!accessToken) return new Response(null, { status: 401 });

  const upstream = await fetch(`${API_BASE_URL}/campo/evidencias/${params.id}/archivo/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    signal: request.signal
  });
  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status === 404 ? 404 : 502 });
  }

  /** @type {Record<string, string>} */
  const headers = {
    'Content-Type': upstream.headers.get('Content-Type') || 'application/octet-stream',
    //  Son fotos de la casa de un cliente: ninguna caché compartida las guarda.
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff'
  };
  const disposicion = upstream.headers.get('Content-Disposition');
  if (disposicion) headers['Content-Disposition'] = disposicion;
  return new Response(upstream.body, { status: 200, headers });
}
