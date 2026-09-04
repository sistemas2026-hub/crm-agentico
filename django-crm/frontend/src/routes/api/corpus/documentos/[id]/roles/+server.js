import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Cambiar a quien se le recupera un documento YA cargado, sin re-vectorizar.
 * Mismo gate de ADMIN que POST /api/corpus/documentos -- ver ese archivo
 * para el porque. Proxy hacia nucleo/canales/api.py: PUT
 * /corpus/documentos/<id>/roles.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function PUT({ params, request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede cambiar los roles de un documento.' }, { status: 403 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json();

  try {
    const resp = await fetch(`${baseUrl}/corpus/documentos/${encodeURIComponent(params.id)}/roles`, {
      method: 'PUT',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ ...cuerpo, tenant })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron actualizar los roles' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
