import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Habilita un documento pendiente para que el asistente pueda recuperarlo.
 *
 * Un documento subido desde /manual entra en estado 'pendiente': se
 * vectoriza, pero asistente.match_chunks no lo devuelve hasta que alguien lo
 * aprueba. Ese filtro vive en SQL, asi que el gate de ADMIN de aca es la
 * SEGUNDA capa, no la unica -- si esta ruta no existiera, el documento
 * seguiria siendo invisible igual.
 *
 * Solo ADMIN, mismo criterio que cambiar los roles de un documento: las dos
 * cosas deciden que contenido puede llegarle a un cliente.
 *
 * 'aprobado_por' viaja desde el servidor y no desde el navegador: quien
 * aprueba lo dice la sesion, no el cliente HTTP.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json(
      { error: 'Solo un administrador puede aprobar un documento.' },
      { status: 403 }
    );
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json(
      { error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 }
    );
  }

  // Quien aprueba se resuelve ACA, nunca llega del navegador -- mismo
  // criterio que /api/asistente con profile_id. Si no se puede identificar,
  // se aprueba igual y queda sin firmante: perder el nombre de quien
  // aprobo es mucho menos grave que dejar un documento colgado sin poder
  // habilitarlo. El 'cuando' queda registrado en cualquier caso.
  let aprobadoPor = null;
  try {
    const perfil = await apiRequest('/profile/', {}, locals);
    aprobadoPor = perfil?.user_obj?.id ?? null;
  } catch {
    aprobadoPor = null;
  }

  try {
    const resp = await fetch(
      `${baseUrl}/corpus/documentos/${encodeURIComponent(params.id)}/aprobar`,
      {
        method: 'POST',
        headers: headersMotor({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ tenant, aprobado_por: aprobadoPor })
      }
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo aprobar el documento' }, {
        status: resp.status
      });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, {
      status: 502
    });
  }
}
