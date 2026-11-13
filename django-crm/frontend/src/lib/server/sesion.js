/**
 * LA SESIÓN DE LA PLATAFORMA: quién es, en qué empresa, y qué pasa cuando el
 * token venció.
 *
 * Hasta el 11/11/2026 esto vivía dentro de `hooks.server.js`, que fuera de
 * SvelteKit no se puede importar, así que ninguna prueba lo recorría. Se mudó
 * acá por el mismo motivo que `sin-cache.js`: para poder afirmar sobre el
 * EFECTO. El hook queda de dos líneas y llama a `atenderSesion()`.
 *
 * CÓMO FUNCIONA
 * - Los tokens viajan en cookies httpOnly: `jwt_access` (dura una hora) y
 *   `jwt_refresh` (catorce días, y el backend lo ROTA en cada uso: el que se
 *   gastó queda en lista negra y vuelve uno nuevo).
 * - Cada pedido verifica el access contra el backend (`verificar-jwt.js`, con
 *   caché por token). Si venció, se renueva con el refresh y se reescriben las
 *   dos cookies.
 *
 * POR QUÉ LA PLATAFORMA «CERRABA SESIÓN SOLA» (11/11/2026)
 * Dos caminos, los dos en la renovación, y ninguno era el refresh venciendo:
 *
 * 1. LA CARRERA DE LA ROTACIÓN. Al cumplirse la hora, el navegador no manda
 *    UN pedido: la Bandeja sondea cada 8 s, abrir una conversación dispara
 *    varias lecturas, y hay más de una pestaña. El primero renueva y el
 *    backend pone el refresh viejo en lista negra. Cualquier otro pedido que
 *    ya había SALIDO con las cookies viejas —y llega después de que el
 *    primero terminó— intenta renovar con el refresh quemado, recibe 401 y
 *    el código BORRABA las tres cookies: las nuevas incluidas. Sesión
 *    cerrada, sin que nada venciera. La deduplicación «en vuelo» solo cubría
 *    los pedidos que se SOLAPABAN con el primero, no los que llegaban un
 *    instante después.
 *
 *    Arreglo: este proceso recuerda unos minutos qué refresh rotó y qué
 *    tokens salieron (`rotadosHacePoco`). Quien llega con el refresh viejo
 *    recibe los mismos tokens nuevos, sin ir al backend. Es lo que el backend
 *    no puede hacer —su lista negra es inmediata— y acá no afloja nada: el
 *    que presenta el refresh viejo es el mismo navegador, el único que lo
 *    tuvo. Y además se renueva ANTES de vencer (`VENTANA_RENOVACION_MS`): así
 *    los pedidos que llegan con el access viejo durante la rotación todavía
 *    lo tienen vigente y no necesitan renovar nada.
 *
 * 2. UNA DEMORA SE TRATABA COMO UN RECHAZO. Si el backend no contestaba la
 *    verificación a tiempo, se renovaba a ciegas; si tampoco contestaba la
 *    renovación, se borraban las cookies. Una Bandeja lenta al cumplirse la
 *    hora era un cierre de sesión. Ahora «sin respuesta» no toca las
 *    cookies: el pedido falla con 503 («la plataforma no responde») y el
 *    siguiente vuelve a intentar con las mismas credenciales. Sigue siendo
 *    fail-closed —sin respuesta no hay sesión en ESE pedido—; lo que ya no
 *    hay es destrucción de credenciales que todavía valen. Solo un rechazo
 *    explícito del backend (401/403) cierra la sesión.
 *
 * Guarda: `sesion.test.js`, que reproduce la carrera y la demora.
 */
import { error, redirect } from '@sveltejs/kit';
import axios from 'axios';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import { comoParametro } from '$lib/destino.js';
import { describeError } from '$lib/server/log-safe.js';
import { verificarTokenDetallado, leerSinVerificar } from '$lib/server/v2/verificar-jwt.js';

// Server-side, so PRIVATE_ over PUBLIC_ -- see the comment in lib/api-helpers.js.
const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Cuánto antes de que venza el access se renueva. Dos minutos cubren de sobra
 * lo que tarda en llegar un pedido que salió con las cookies viejas (segundos)
 * y son nada frente a la hora que dura el token.
 */
export const VENTANA_RENOVACION_MS = 2 * 60 * 1000;

/**
 * Cuánto se recuerda una rotación. Un pedido que salió del navegador con el
 * refresh viejo llega en segundos; tres minutos es margen, no necesidad.
 */
export const MEMORIA_ROTACION_MS = 3 * 60 * 1000;

/** Las rutas que no piden sesión. Ver el porqué de cada una en el historial del hook. */
const RUTAS_PUBLICAS = ['/login', '/logout', '/bounce', '/portal', '/csat', '/solicitud'];
/** Piden sesión pero no empresa. */
const RUTAS_SOLO_SESION = ['/org'];

const UN_DIA = 60 * 60 * 24;
const UN_ANIO = UN_DIA * 365;
const COOKIE = {
  path: '/',
  httpOnly: true,
  sameSite: /** @type {const} */ ('lax'),
  secure: process.env.NODE_ENV === 'production'
};

/**
 * @typedef {{ default_currency?: string, currency_symbol?: string, default_country?: string|null }} OrgSettingsPayload
 * @typedef {{ org_id?: string, org_name?: string, role?: string, user_id?: string, user_name?: string, user_email?: string, user_profile_pic?: string, exp?: number, iat?: number, org_settings?: OrgSettingsPayload }} JWTPayload
 * @typedef {{ estado: 'renovado', access: string, refresh?: string }
 *         | { estado: 'rechazado' }
 *         | { estado: 'sin_respuesta' }} Refresco
 */

/** @param {import('@sveltejs/kit').Cookies} cookies @param {string} access @param {string | undefined} refresh */
function guardarTokens(cookies, access, refresh) {
  cookies.set('jwt_access', access, { ...COOKIE, maxAge: UN_DIA });
  if (refresh) cookies.set('jwt_refresh', refresh, { ...COOKIE, maxAge: UN_ANIO });
}

/** @param {import('@sveltejs/kit').Cookies} cookies */
function borrarSesion(cookies) {
  cookies.delete('jwt_access', { path: '/' });
  cookies.delete('jwt_refresh', { path: '/' });
  cookies.delete('org', { path: '/' });
}

/** @param {JWTPayload | null} payload */
function porVencer(payload) {
  const exp = typeof payload?.exp === 'number' ? payload.exp * 1000 : 0;
  return exp - Date.now() < VENTANA_RENOVACION_MS;
}

// ---------------------------------------------------------------------------
// La renovación
// ---------------------------------------------------------------------------

/** Renovaciones en curso, por refresh token: los pedidos que se solapan comparten una. */
/** @type {Map<string, Promise<Refresco>>} */
const enVuelo = new Map();

/** Rotaciones recientes: refresh viejo -> los tokens que salieron en su lugar. */
/** @type {Map<string, { hasta: number, access: string, refresh: string }>} */
const rotadosHacePoco = new Map();

function podarRotaciones() {
  const ahora = Date.now();
  for (const [viejo, r] of rotadosHacePoco) {
    if (r.hasta <= ahora) rotadosHacePoco.delete(viejo);
  }
}

/**
 * Renueva el access con el refresh. UNA sola ida al backend por refresh token,
 * aunque lleguen varios pedidos con el mismo: los que se solapan esperan la
 * misma promesa, y los que llegan después —dentro de `MEMORIA_ROTACION_MS`—
 * reciben lo que ya salió. Un refresh que el backend rechaza de verdad se
 * informa como `rechazado`; uno que no contesta, como `sin_respuesta`, y las
 * dos cosas no se tratan igual aguas arriba.
 *
 * @param {string} refreshToken
 * @returns {Promise<Refresco>}
 */
export function refrescar(refreshToken) {
  const reciente = rotadosHacePoco.get(refreshToken);
  if (reciente && reciente.hasta > Date.now()) {
    return Promise.resolve({ estado: 'renovado', access: reciente.access, refresh: reciente.refresh });
  }

  const existente = enVuelo.get(refreshToken);
  if (existente) return existente;

  const pendiente = pedirRefresco(refreshToken)
    .then((r) => {
      if (r.estado === 'renovado' && r.refresh) {
        podarRotaciones();
        rotadosHacePoco.set(refreshToken, {
          hasta: Date.now() + MEMORIA_ROTACION_MS,
          access: r.access,
          refresh: r.refresh
        });
      }
      return r;
    })
    .finally(() => enVuelo.delete(refreshToken));
  enVuelo.set(refreshToken, pendiente);
  return pendiente;
}

/**
 * @param {string} refreshToken
 * @returns {Promise<Refresco>}
 */
async function pedirRefresco(refreshToken) {
  try {
    const r = await axios.post(
      `${API_BASE_URL}/auth/refresh-token/`,
      { refresh: refreshToken },
      { timeout: 10000, validateStatus: (s) => s === 200 || s === 401 || s === 403 }
    );
    if (r.status !== 200 || !r.data?.access) {
      // El backend decidió: el refresh está vencido, en lista negra, o la
      // cuenta ya no puede entrar. Esto SÍ cierra la sesión.
      console.warn({ tipo: 'sesion_refresh_rechazado', status: r.status });
      return { estado: 'rechazado' };
    }
    return { estado: 'renovado', access: r.data.access, refresh: r.data.refresh };
  } catch (e) {
    // Nunca el error crudo: su `config.data` ES el refresh token.
    console.error('Token refresh failed:', describeError(e));
    return { estado: 'sin_respuesta' };
  }
}

/** Solo para pruebas. */
export function _olvidarRotaciones() {
  enVuelo.clear();
  rotadosHacePoco.clear();
}

// ---------------------------------------------------------------------------
// La empresa
// ---------------------------------------------------------------------------

/**
 * Cambia de empresa y trae tokens con ese contexto. Manda el refresh saliente
 * para que el backend lo retire; si no, seguiría valiendo contra la empresa
 * anterior el resto de su vida.
 *
 * @param {string} accessToken
 * @param {string} orgId
 * @param {string} [refreshToken]
 * @returns {Promise<{ access_token: string, refresh_token: string, current_org?: { id: string, name: string } } | null>}
 */
async function cambiarDeEmpresa(accessToken, orgId, refreshToken) {
  try {
    const r = await axios.post(
      `${API_BASE_URL}/auth/switch-org/`,
      refreshToken ? { org_id: orgId, refresh: refreshToken } : { org_id: orgId },
      { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
    );
    return r.data;
  } catch (e) {
    // Nunca el error crudo: sus `config.headers` llevan el JWT.
    console.error('Org switch failed:', describeError(e));
    return null;
  }
}

/** @param {string} token @param {string} orgId */
function tokenTieneEmpresa(token, orgId) {
  // Lee claims sin verificar, y puede: solo se llama sobre un token que la
  // verificación ya aceptó. Sobre un token verificado, los claims valen.
  const payload = leerSinVerificar(token)?.payload ?? null;
  return Boolean(payload && payload.org_id === orgId);
}

// ---------------------------------------------------------------------------
// El turno completo
// ---------------------------------------------------------------------------

/**
 * Arma `locals.user` / `locals.org` a partir de las cookies, renueva lo que
 * haya que renovar, y corta el pedido si la ruta exige lo que no hay.
 *
 * @param {Pick<import('@sveltejs/kit').RequestEvent, 'cookies' | 'url' | 'locals'>} event
 */
export async function atenderSesion(event) {
  const { cookies, url } = event;
  let accessToken = cookies.get('jwt_access');
  let refreshToken = cookies.get('jwt_refresh');
  const orgId = cookies.get('org');

  /** @type {JWTPayload | null} */
  let jwtPayload = null;
  // El backend no contestó: no se puede afirmar la sesión, pero tampoco negarla.
  let sinRespuesta = false;

  if (accessToken) {
    const verificacion = await verificarTokenDetallado(accessToken);

    if (verificacion.estado === 'valido') {
      jwtPayload = verificacion.payload;
      // Vigente pero por vencer: se renueva ya, en un pedido que todavía tiene
      // sesión. Si no se puede, la sesión vigente sigue valiendo lo que le
      // queda; nada se borra por un refresh que no salió.
      if (refreshToken && porVencer(jwtPayload)) {
        const r = await refrescar(refreshToken);
        if (r.estado === 'renovado') {
          guardarTokens(cookies, r.access, r.refresh);
          accessToken = r.access;
          refreshToken = r.refresh ?? refreshToken;
          // Token recién EMITIDO por el backend en respuesta a este pedido:
          // su procedencia es la respuesta, no una cookie del navegador.
          jwtPayload = leerSinVerificar(r.access)?.payload ?? jwtPayload;
        }
      }
    } else if (verificacion.estado === 'invalido') {
      if (refreshToken) {
        const r = await refrescar(refreshToken);
        if (r.estado === 'renovado') {
          guardarTokens(cookies, r.access, r.refresh);
          accessToken = r.access;
          refreshToken = r.refresh ?? refreshToken;
          jwtPayload = leerSinVerificar(r.access)?.payload ?? null;
        } else if (r.estado === 'rechazado') {
          // El único camino que cierra la sesión: el backend dijo que no.
          borrarSesion(cookies);
        } else {
          sinRespuesta = true;
        }
      }
    } else {
      sinRespuesta = true;
    }
  }

  if (jwtPayload) {
    event.locals.user = {
      id: jwtPayload.user_id,
      name: jwtPayload.user_name || '',
      email: jwtPayload.user_email || '',
      profilePhoto: jwtPayload.user_profile_pic || ''
    };

    if (orgId && !UUID_RE.test(orgId)) {
      cookies.delete('org', { path: '/' });
    } else if (orgId) {
      const token = /** @type {string} */ (accessToken);

      if (tokenTieneEmpresa(token, orgId)) {
        event.locals.org = { id: jwtPayload.org_id || orgId, name: jwtPayload.org_name || 'Organization' };
        /** @type {any} */ (event.locals).profile = { org: event.locals.org, role: jwtPayload.role || 'USER' };
        event.locals.org_name = jwtPayload.org_name || 'Organization';
        event.locals.org_settings = jwtPayload.org_settings || {
          default_currency: 'USD',
          currency_symbol: '$',
          default_country: null
        };
      } else {
        const cambio = await cambiarDeEmpresa(token, orgId, refreshToken);

        if (cambio) {
          guardarTokens(cookies, cambio.access_token, cambio.refresh_token);
          event.locals.org = cambio.current_org;
          // El token recién emitido trae el rol y los ajustes de ESTA empresa;
          // asumir 'USER' le quitaría a un admin su menú en la primera
          // navegación después del cambio.
          const nuevo = leerSinVerificar(cambio.access_token)?.payload ?? null;
          /** @type {any} */ (event.locals).profile = { org: cambio.current_org, role: nuevo?.role || 'USER' };
          event.locals.org_name = cambio.current_org?.name || 'Organization';
          event.locals.org_settings = nuevo?.org_settings || {
            default_currency: 'USD',
            currency_symbol: '$',
            default_country: null
          };
        } else {
          // La cookie de empresa ya no vale. Conserva el destino: quien venía
          // de un enlace profundo tiene tanto derecho a volver ahí como el que
          // fue rebotado por no tener sesión.
          cookies.delete('org', { path: '/' });
          throw redirect(303, `/org${comoParametro(url.pathname + (url.search || ''))}`);
        }
      }
    }
  }

  // --- La guarda de ruta ---
  const pathname = url.pathname;
  const esPublica = RUTAS_PUBLICAS.some((r) => pathname === r || pathname.startsWith(r + '/'));
  const esSoloSesion = RUTAS_SOLO_SESION.some((r) => pathname === r || pathname.startsWith(r + '/'));
  if (esPublica) return;

  if (!jwtPayload && sinRespuesta) {
    // Había credenciales y nadie pudo decir si valen. No es «sin sesión»: es
    // «sin backend», y mandar a /login (borrando o no) le cobraría a la
    // persona una demora que no es suya.
    throw error(503, 'La plataforma no responde en este momento. Tu sesión sigue abierta: volvé a intentar en unos segundos.');
  }

  // A dónde quería ir, para poder devolverlo ahí. Se valida en destinoSeguro().
  const volverA = comoParametro(pathname + (url.search || ''));
  if (!jwtPayload) throw redirect(307, `/login${volverA}`);
  if (!esSoloSesion && !event.locals.org) throw redirect(307, `/org${volverA}`);
}
