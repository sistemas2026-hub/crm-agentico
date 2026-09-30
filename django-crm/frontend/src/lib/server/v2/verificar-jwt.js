import axios from 'axios';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

/**
 * Verificación REAL del JWT de sesión.
 *
 * POR QUÉ EXISTE ESTE ARCHIVO
 * ---------------------------
 * Hasta el 21/09/2026 la sesión se resolvía decodificando el token y mirando
 * `exp`. Nada verificaba la firma. Eso significa que un `jwt_access` fabricado
 * a mano —sin ninguna clave— producía un `locals.user` válido, y de ahí sale
 * `autorDeSesion()`: el nombre y el id que el motor guarda como AUTOR de cada
 * acción del relevo. Quien tomó la conversación, quién aprobó la acción, quién
 * la cerró y con qué desenlace.
 *
 * El motor no puede detectarlo: autentica al SERVICIO (`X-Servicio-Token`), no
 * al usuario. La identidad viaja en el cuerpo. Si acá no se verifica, no se
 * verifica en ningún lado.
 *
 * POR QUÉ SE VERIFICA CONTRA EL BACKEND Y NO CON UNA CLAVE ACÁ
 * ------------------------------------------------------------
 * Django firma con HS256 y `SIGNING_KEY = SECRET_KEY` (crm/settings.py). Es
 * simétrica: verificarla acá exigiría copiar la clave maestra de Django al
 * frontend. Una clave que firma tokens y además cifra sesiones, en un segundo
 * proceso, multiplica por dos las formas de perderla — y no hay JWKS ni clave
 * pública que usar en su lugar.
 *
 * Así que se le pregunta a quien ya sabe: `GET /api/auth/me/` usa
 * `JWTAuthentication` + `IsAuthenticated`, o sea que valida firma y expiración
 * con la clave que ya tiene. Un 200 prueba que el token es auténtico; un 401
 * prueba que no. Ningún secreto nuevo cambia de casa.
 *
 * EL COSTO, Y POR QUÉ SE PAGA
 * ---------------------------
 * El código anterior evitaba esta llamada a propósito ("LOCAL JWT DECODE - no
 * API call!"). La cachea: los access token duran una hora y son inmutables, así
 * que verificar el mismo dos veces no aporta nada. Con caché, es una llamada
 * por token y no por request.
 *
 * Una verificación que se saltea por rendimiento no es una verificación.
 */

const API_BASE_URL = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

/** Lo único que el backend firma y nosotros aceptamos. */
const ALGORITMOS_ACEPTADOS = new Set(['HS256']);

/**
 * Cuánto se recuerda que un token era válido. Los access token duran una hora
 * y no se pueden revocar (sólo los refresh se ponen en lista negra), así que
 * este tope no protege contra una revocación —no existe— sino que acota el
 * daño si alguna vez se agrega una: cinco minutos es lo que tardaría en
 * hacerse efectiva.
 */
const TTL_CACHE_MS = 5 * 60 * 1000;

/** @type {Map<string, { hasta: number, payload: any }>} */
const verificados = new Map();

/** Verificaciones en vuelo, para no pedir N veces el mismo token a la vez. */
/** @type {Map<string, Promise<any>>} */
const enVuelo = new Map();

/**
 * Lee la cabecera y el cuerpo SIN verificar nada.
 *
 * NO ES AUTORIDAD DE AUTENTICACIÓN y no puede volver a serlo: sirve para
 * rechazar barato lo que ni siquiera tiene forma de token, y para leer claims
 * DESPUÉS de que la firma se haya verificado. Nunca antes.
 *
 * @param {string} token
 * @returns {{ header: any, payload: any } | null}
 */
export function leerSinVerificar(token) {
  try {
    const partes = String(token || '').split('.');
    if (partes.length !== 3) return null;
    const decodificar = (p) =>
      JSON.parse(Buffer.from(p.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'));
    return { header: decodificar(partes[0]), payload: decodificar(partes[1]) };
  } catch {
    return null;
  }
}

/**
 * Los rechazos que se pueden decidir sin salir a la red. Devuelve el motivo, o
 * null si hay que preguntarle al backend.
 *
 * Son un filtro, no la verificación: que pasen no dice nada sobre la firma.
 *
 * @param {string} token
 * @returns {string|null}
 */
export function motivoDeRechazoLocal(token) {
  const partes = leerSinVerificar(token);
  if (!partes) return 'malformado';

  // 'alg: none' y los parientes: un token que declara no estar firmado no se
  // manda a verificar, se descarta. Y un algoritmo que el backend no usa
  // tampoco -- aceptarlo abriría la confusión de algoritmos.
  const alg = partes.header?.alg;
  if (!alg || !ALGORITMOS_ACEPTADOS.has(String(alg))) return 'algoritmo_inesperado';

  const exp = partes.payload?.exp;
  if (typeof exp !== 'number' || exp * 1000 <= Date.now()) return 'expirado';

  return null;
}

/**
 * ¿El backend reconoce este token? Devuelve el payload verificado, o null.
 *
 * FAIL-CLOSED: si el backend no responde, no se puede afirmar que el token sea
 * válido, así que no lo es. Una caída del backend cierra sesiones; darlas por
 * buenas convertiría cada caída en una ventana sin autenticación.
 *
 * @param {string} token
 * @returns {Promise<any|null>}
 */
export async function verificarToken(token) {
  if (!token) return null;

  const motivo = motivoDeRechazoLocal(token);
  if (motivo) return null;

  const recordado = verificados.get(token);
  if (recordado && recordado.hasta > Date.now()) return recordado.payload;

  const yaPedido = enVuelo.get(token);
  if (yaPedido) return yaPedido;

  const promesa = (async () => {
    try {
      const r = await axios.get(`${API_BASE_URL}/auth/me/`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 8000,
        validateStatus: (s) => s === 200 || s === 401 || s === 403
      });
      if (r.status !== 200) return null;

      // El backend acepto el token: la firma es autentica y recien AHORA los
      // claims valen. De aca en mas se pueden leer sin miedo.
      const { payload } = leerSinVerificar(token) ?? {};
      if (!payload) return null;

      const exp = typeof payload.exp === 'number' ? payload.exp * 1000 : 0;
      verificados.set(token, {
        hasta: Math.min(Date.now() + TTL_CACHE_MS, exp),
        payload
      });
      return payload;
    } catch {
      // Sin respuesta no hay verificacion, y sin verificacion no hay sesion.
      return null;
    } finally {
      enVuelo.delete(token);
    }
  })();

  enVuelo.set(token, promesa);
  return promesa;
}

/** Sólo para pruebas: vacía lo recordado. */
export function _olvidarVerificados() {
  verificados.clear();
  enVuelo.clear();
}
