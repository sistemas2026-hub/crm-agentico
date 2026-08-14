import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';

/**
 * Proxy hacia el motor del asistente (crm-agentico, repo aparte, ver
 * PRIVATE_ASISTENTE_URL en .env.docker.local). El browser nunca le habla
 * directo -- ni conoce su URL ni necesita CORS -- se reenvia
 * server-to-server, mismo patron que /api/search.
 *
 * Antes esto mandaba `rol: 'soporte'` fijo, asi que los otros agentes
 * configurados (facturacion, administracion) no eran alcanzables por nadie:
 * quien preguntaba por una factura le hablaba a un agente sin
 * consultar_facturas. Ahora se manda QUIEN pregunta y el motor resuelve que
 * agentes tiene asignados, fusionandolos si son varios.
 *
 * EL profile_id SE RESUELVE ACA, NUNCA LLEGA DEL CLIENTE. Es lo que decide a
 * que datos accede el turno: si viniera en el cuerpo de la peticion,
 * cualquiera podria mandar el de otra persona y quedarse con sus agentes.
 * Cuesta una llamada extra al backend por mensaje, en red interna y de pocos
 * milisegundos -- despreciable al lado de los 5-12 s que tarda un turno.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { mensaje } = await request.json();
  if (!mensaje) {
    return json({ error: 'Falta el mensaje' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  /** @type {string | undefined} */
  let profileId;
  try {
    const perfil = await apiRequest('/profile/', {}, locals);
    profileId = perfil?.user_obj?.id;
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo identificar tu perfil' }, { status: 502 });
  }
  if (!profileId) {
    return json({ error: 'No se pudo identificar tu perfil en esta organizacion' },
      { status: 403 });
  }

  try {
    const resp = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant,
        profile_id: profileId,
        identificador_sesion: locals.user.id,
        mensaje
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'El asistente no respondio' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
