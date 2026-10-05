import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { claveDeSesion, bloqueDeContexto, mensajeParaElMotor } from '$lib/supervisor/chat-sesion.js';

/**
 * EL CANAL DE LA BURBUJA DEL SUPERVISOR NOC
 * ==========================================
 *
 * GET   recupera el hilo persistido de esta persona.
 * POST  manda un mensaje y devuelve la respuesta.
 *
 * MISMO PATRON QUE /api/asistente, Y DOS DIFERENCIAS DELIBERADAS
 * ---------------------------------------------------------------
 *  1. La clave de sesion lleva prefijo ('snoc:<user.id>'). Sin eso las dos
 *     pantallas escribirian en el mismo hilo del motor -- ver la nota en
 *     lib/supervisor/chat-sesion.js.
 *  2. Antes de preguntar se lee el estado del Supervisor y viaja con la
 *     pregunta. Dexter conoce WispHub y SmartOLT por su catalogo, pero no ve
 *     las propuestas ni los indicadores: eso es lo unico que esta pantalla
 *     sabe y el motor no.
 *
 * LA IDENTIDAD NO SE ACEPTA DEL NAVEGADOR, NUNCA
 * -----------------------------------------------
 * 'profile_id', el nombre y el tenant se resuelven aca, del lado del
 * servidor: son lo que decide a que datos accede el turno. Si viajaran en el
 * cuerpo, cualquiera podria mandar el de otra persona y quedarse con sus
 * agentes. La clave de sesion se deriva de 'locals.user.id' por la misma
 * razon -- aceptarla del cliente seria poder leer la conversacion de otro.
 *
 * 'apiRequest' RECIBE 'cookies', NO 'locals'
 * -------------------------------------------
 * Medido el 05/10/2026 contra produccion, con la burbuja ya desplegada: la
 * primera pregunta devolvio
 *
 *     "Organization context is required. Please login again."
 *
 * 'apiRequest' saca el JWT con 'locals.cookies || locals' y despues
 * 'cookies.get("jwt_access")'. En un '+server.js' el evento trae 'cookies'
 * APARTE de 'locals', y 'hooks.server.js' solo deja ahi user/org/org_name/
 * org_settings -- nunca 'cookies'. O sea que el fallback agarraba 'locals',
 * '.get' no existia, no salia cabecera 'Authorization' y Django respondia
 * 403. El sintoma ("volve a iniciar sesion") senala al login, que estaba
 * perfecto.
 *
 * El patron correcto es el que ya usaba 'lib/server/v2/supervisor-noc.js':
 * pasar '{ cookies }'. Esto NO sigue a '/api/asistente/+server.js', que pasa
 * 'locals' y tiene el mismo defecto latente sin corregir.
 */

/** Cuantos mensajes se recuperan al abrir la burbuja. */
const LIMITE_HISTORIAL = 60;

/**
 * Lo que hace falta para hablarle al motor, resuelto del lado del servidor.
 * Devuelve { error, status } si algo falta -- quien llama lo propaga tal cual
 * en vez de continuar con una identidad a medias.
 *
 * @param {any} locals
 * @param {typeof globalThis.fetch} fetch
 */
async function identidad(locals, fetch) {
  if (!locals.user) return { error: 'No autenticado', status: 401 };

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return { error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)', status: 500 };
  }

  const sesion = claveDeSesion(locals.user);
  if (!sesion) return { error: 'No se pudo identificar tu sesion', status: 403 };

  return { baseUrl, tenant, sesion };
}

/**
 * El estado del Supervisor, para que la pregunta no llegue sin contexto.
 *
 * NUNCA LEVANTA Y NUNCA BLOQUEA. Si el CRM no contesta se devuelve null y la
 * pregunta viaja sola: una respuesta sin contexto sirve mas que un chat
 * caido porque una consulta de indicadores fallo. Se distingue de un cero --
 * ver 'bloqueDeContexto'.
 *
 * Usa los endpoints que YA existen, con los permisos y el tenant de quien
 * pregunta: no hay una segunda puerta a los datos del Supervisor.
 *
 * @param {import('@sveltejs/kit').Cookies} cookies
 */
async function estadoDelSupervisor(cookies) {
  /** @type {{abiertas?: number, criticas?: number, indicadores?: Record<string, any>}} */
  const estado = {};
  try {
    const propuestas = await apiRequest('/operaciones/propuestas/?estado=propuesta', {}, { cookies });
    const filas = Array.isArray(propuestas) ? propuestas : (propuestas?.results ?? []);
    if (Array.isArray(filas)) {
      estado.abiertas = filas.length;
      estado.criticas = filas.filter((p) => Number(p?.prioridad ?? 0) >= 60).length;
    }
  } catch {
    //  Silencio deliberado: ver la docstring. No se registra el detalle
    //  porque puede traer datos de la operacion.
  }
  try {
    const ind = await apiRequest('/operaciones/indicadores/', {}, { cookies });
    if (ind && typeof ind === 'object') {
      const plano = {};
      for (const [k, v] of Object.entries(ind)) {
        if (typeof v === 'number' || typeof v === 'string') plano[k] = v;
      }
      if (Object.keys(plano).length) estado.indicadores = plano;
    }
  } catch {
    /* igual que arriba */
  }
  return Object.keys(estado).length ? estado : null;
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ locals, fetch }) {
  const id = await identidad(locals, fetch);
  if (id.error) return json({ error: id.error }, { status: id.status });

  const url = new URL(`${id.baseUrl}/chat/historial`);
  url.searchParams.set('tenant', id.tenant);
  url.searchParams.set('identificador_sesion', id.sesion);
  url.searchParams.set('limite', String(LIMITE_HISTORIAL));

  try {
    const resp = await fetch(url, { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer el historial' },
        { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 });
  }
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, locals, cookies, fetch }) {
  const id = await identidad(locals, fetch);
  if (id.error) return json({ error: id.error }, { status: id.status });

  const { mensaje } = await request.json();
  if (!mensaje || !String(mensaje).trim()) {
    return json({ error: 'Falta el mensaje' }, { status: 400 });
  }

  /** @type {string | undefined} */
  let profileId;
  let nombreColaborador = '';
  try {
    const perfil = await apiRequest('/profile/', {}, { cookies });
    profileId = perfil?.user_obj?.id;
    nombreColaborador = (perfil?.user_obj?.name || perfil?.user_obj?.email || '').trim();
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo identificar tu perfil' },
      { status: 502 });
  }
  if (!profileId) {
    return json({ error: 'No se pudo identificar tu perfil en esta organizacion' },
      { status: 403 });
  }

  const contexto = bloqueDeContexto(await estadoDelSupervisor(cookies));

  try {
    const resp = await fetch(`${id.baseUrl}/chat`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant: id.tenant,
        profile_id: profileId,
        identificador_sesion: id.sesion,
        nombre_colaborador: nombreColaborador,
        mensaje: mensajeParaElMotor(String(mensaje), contexto)
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'El Supervisor no respondio' },
        { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 });
  }
}
