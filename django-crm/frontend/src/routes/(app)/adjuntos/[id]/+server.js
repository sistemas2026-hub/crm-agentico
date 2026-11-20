import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

/**
 * Sirve el archivo de un adjunto del CRM.
 *
 * POR QUE NO SE ENLAZA LA API DIRECTO. El token vive en una cookie httpOnly
 * del origen de SvelteKit; el navegador no la manda al host de la API, y la
 * API no acepta sesión (`DEFAULT_AUTHENTICATION_CLASSES` no trae
 * `SessionAuthentication`). Un `<a href>` a
 * `agent-api…/api/attachments/…/archivo/` llegaría sin credencial y daría 401.
 * Mismo motivo y misma forma que `invoices/[id]/pdf`.
 *
 * POR QUE NO SE ENLAZA `/media/` TAMPOCO. Era lo que había hasta el
 * 07/11/2026, y daba 404: `crm/urls.py` sirve `/media/` solo con DEBUG. Y
 * encenderlo dejaría la foto de la casa de un cliente en una URL pública y
 * adivinable. Ver `common/views/attachment_views.py`.
 *
 * LA AUTORIZACIÓN SIGUE SIENDO DE LA API: filtra por la empresa del perfil,
 * así que un adjunto de otro equipo contesta 404 también acá. Esta ruta
 * transporta la credencial; no decide.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ params, cookies }) {
  const token = cookies.get('jwt_access');
  if (!token) error(401, 'No iniciaste sesión.');

  const apiUrl = env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL;
  const upstream = await fetch(`${apiUrl}/api/attachments/${params.id}/archivo/`, {
    headers: { Authorization: `Bearer ${token}` }
  });

  if (!upstream.ok) {
    // 403 y 404 colapsan a 404: no se confirma que un archivo existe a quien
    // no puede verlo.
    if (upstream.status === 403 || upstream.status === 404) {
      error(404, 'Ese archivo no existe, o es de otro equipo.');
    }
    error(502, 'No se pudo abrir el archivo.');
  }

  const body = await upstream.arrayBuffer();
  const headers = {
    'Content-Type': upstream.headers.get('content-type') ?? 'application/octet-stream',
    // La foto de la casa de un cliente no queda en una caché compartida.
    'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff'
  };
  const disposicion = upstream.headers.get('content-disposition');
  if (disposicion) headers['Content-Disposition'] = disposicion;
  return new Response(body, { headers });
}
