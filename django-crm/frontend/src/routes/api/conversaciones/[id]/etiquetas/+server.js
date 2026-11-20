import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Las etiquetas del equipo del chat de esta conversación (11/11/2026). Ver
 * nucleo/canales/api.py: PUT /conversaciones/<id>/etiquetas.
 *
 * Del navegador viene SOLO la lista de claves. Quién las cambió sale de la
 * sesión (autorDeSesion), nunca del cuerpo: queda guardado como
 * 'cambiada_por' en el chat. Cuáles claves existen lo decide el motor contra
 * el catálogo de la empresa (400 si alguna no está); acá solo se descarta lo
 * que no es texto, para que el motor reciba una lista y no otra cosa.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function PUT({ request, params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }
  const cuerpo = await request.json().catch(() => ({}));
  const etiquetas = Array.isArray(cuerpo?.etiquetas)
    ? cuerpo.etiquetas.filter((/** @type {unknown} */ c) => typeof c === 'string')
    : null;
  if (!etiquetas) {
    return json({ error: "'etiquetas' tiene que ser una lista de claves." }, { status: 400 });
  }
  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/etiquetas`, {
      method: 'PUT',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ tenant, etiquetas, ...autorDeSesion(locals) })
    });
    const datos = await resp.json().catch(() => ({}));
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
