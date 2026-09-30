/**
 * PRIVACIDAD DE LA OBSERVABILIDAD -- lo que puede salir hacia un proveedor
 * externo de monitoreo (Sentry u otro), y lo que nunca.
 *
 * El criterio, en una frase: la telemetria tiene que responder "que fallo"
 * sin poder responder "quien era el cliente". Dexter procesa conversaciones
 * reales de clientes de un ISP; en pantalla hay nombres, telefonos o
 * identificadores de canal, cedulas escritas por el cliente en el hilo, y
 * paneles de identidad. Nada de eso es un dato de operacion.
 *
 * Por que un modulo puro y no opciones sueltas en los `init`: para poder
 * AFIRMARLO sin proveedor, sin red y sin build (privacidad.test.js inyecta
 * nombres, telefonos, cedulas y mensajes y exige que no salgan por ningun
 * gancho). El mismo modulo lo usan hooks.client.js e instrumentation.server.js,
 * asi que hay una sola verdad sobre que se limpia.
 *
 * Dos capas, porque ninguna alcanza sola:
 *   1. PATRONES sobre cualquier texto: correos, BSUID, wamid, JWT, telefonos,
 *      cadenas de digitos (cedulas, cuentas). Una regex no sabe que "Juan
 *      Perez" es un nombre.
 *   2. VOCABULARIO: un mensaje de error que hable de "cliente", "titular",
 *      "cedula"... se reemplaza entero por un marcador con hash. Se pierde
 *      legibilidad en ese caso puntual; se conserva agrupacion y el stack.
 *      El stack (archivo, funcion, linea) es lo que de verdad dice que fallo.
 *
 * Ademas, las CLAVES que por nombre cargan datos del cliente o secretos se
 * eliminan de los payloads libres (extra, contexts, tags, data de migas y
 * spans, atributos de logs). Los campos estructurales de Sentry (message,
 * exception, request) se tratan uno por uno, no por lista.
 *
 * Todo falla cerrado: si limpiar revienta, el evento no sale.
 */

const MARCADOR = 'mensaje omitido (posible dato personal)';
const LARGO_MAXIMO = 500;
const PROFUNDIDAD_MAXIMA = 6;

/** Claves que, por su nombre, cargan datos personales o secretos. */
export const CLAVES_PROHIBIDAS = new Set([
  // identidad del cliente
  'nombre', 'nombres', 'nombre_cliente', 'apellido', 'apellidos', 'titular',
  'cedula', 'documento', 'dni', 'nit', 'identificacion',
  'telefono', 'celular', 'phone', 'usuario_externo', 'remitente', 'wa_id', 'wamid',
  'correo', 'email', 'mail', 'direccion', 'address',
  'coordenadas', 'latitude', 'longitude', 'lat', 'lng', 'geo',
  // texto de la conversacion y respuestas del ISP
  'texto', 'contenido', 'cuerpo', 'mensaje', 'mensajes', 'respuesta', 'respuestas',
  'historial', 'transcripcion', 'conversacion', 'conversation', 'cliente', 'customer',
  // secretos y sesion
  'cookie', 'cookies', 'headers', 'authorization', 'token', 'jwt_access', 'jwt_refresh',
  'password', 'contrasena', 'clave', 'secret', 'api_key', 'apikey',
  'user', 'usuario', 'ip', 'ip_address', 'autor_nombre'
]);

/**
 * Palabras que, en un mensaje de error, indican que habla de una persona.
 * Sin tildes y en minuscula: asi se compara.
 */
const VOCABULARIO_SENSIBLE = [
  'cliente', 'titular', 'cedula', 'telefono', 'celular', 'nombre', 'apellido',
  'documento', 'correo', 'direccion', 'whatsapp', 'remitente', 'usuario'
];

/** Orden: lo especifico antes que lo generico (el generico se comeria lo demas). */
const PATRONES = [
  [/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, '<correo>'],
  [/\bCO\.\d{6,}\b/g, '<bsuid>'],
  [/\bwamid\.[A-Za-z0-9+/=]+/gi, '<wamid>'],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g, '<jwt>'],
  [/(?:\+?57[\s.-]?)?\b3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}\b/g, '<telefono>'],
  [/\b\d{6,}\b/g, '<numero>']
];

/** Errores que no son de Dexter: extensiones del navegador. */
export const ERRORES_IGNORADOS = [
  /Extension context invalidated/,
  /message channel closed before a response was received/,
  /ResizeObserver loop/
];

/** Selectores que el replay BLOQUEA (no se graba ni la forma). */
export const SELECTORES_PRIVADOS = ['[data-privado]', '.v2-main', '.mesa.bandeja', '.hoja'];

/** Opciones del replay: todo el texto enmascarado, entradas enmascaradas,
 *  medios bloqueados, pantallas con datos bloqueadas, ningun cuerpo de red. */
export const OPCIONES_REPLAY = Object.freeze({
  maskAllText: true,
  maskAllInputs: true,
  blockAllMedia: true,
  block: SELECTORES_PRIVADOS,
  networkDetailAllowUrls: []
});

function sinTildes(texto) {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/** Hash chico y estable, para agrupar sin conservar el texto (FNV-1a). */
function huella(texto) {
  let h = 0x811c9dc5;
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0').slice(0, 6);
}

/** Capa 1: reemplaza por marcador todo lo que tenga forma de dato personal. */
export function redactarTexto(texto) {
  if (typeof texto !== 'string') return texto;
  let salida = texto.length > LARGO_MAXIMO ? texto.slice(0, LARGO_MAXIMO) + '…' : texto;
  for (const [patron, marcador] of PATRONES) salida = salida.replace(patron, marcador);
  return salida;
}

/**
 * Palabras con mayuscula que NO son nombres de personas: las frases de estado
 * HTTP ("Not Found", "Bad Gateway") y las siglas que aparecen en mensajes de
 * error. Todo lo demas que venga en mayuscula, de a dos o mas seguidas, se
 * trata como un posible nombre.
 */
const MAYUSCULAS_PERMITIDAS = new Set([
  // frases de estado HTTP
  'ok', 'created', 'accepted', 'no', 'content', 'moved', 'permanently', 'found', 'see', 'other',
  'not', 'modified', 'temporary', 'redirect', 'bad', 'request', 'unauthorized', 'payment',
  'required', 'forbidden', 'method', 'allowed', 'acceptable', 'timeout', 'conflict', 'gone',
  'length', 'precondition', 'failed', 'payload', 'too', 'large', 'unsupported', 'media', 'type',
  'range', 'satisfiable', 'expectation', 'unprocessable', 'entity', 'locked', 'many', 'requests',
  'internal', 'server', 'error', 'implemented', 'gateway', 'service', 'unavailable', 'continue',
  'switching', 'protocols', 'partial', 'multiple', 'choices', 'reset',
  // siglas y palabras tecnicas
  'api', 'http', 'https', 'json', 'url', 'jwt', 'dns', 'tls', 'ssl', 'css', 'dom', 'ui', 'id',
  'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'cors', 'xhr', 'sdk', 'pii', 'dsn',
  'isp', 'onu', 'ont', 'olt', 'crm', 'tv', 'ip', 'mac', 'wifi', 'pon', 'catv', 'sn', 'uuid',
  'type', 'range', 'error', 'failed', 'fetch', 'network', 'timeout', 'abort', 'aborted',
  // navegadores y sistemas, que Sentry manda como contexto ("Mobile Safari")
  'chrome', 'chromium', 'firefox', 'safari', 'edge', 'opera', 'mobile', 'samsung', 'internet',
  'explorer', 'windows', 'android', 'ios', 'linux', 'ubuntu', 'debian', 'mac', 'os', 'x',
  'iphone', 'ipad', 'pixel', 'galaxy', 'node', 'deno', 'bun'
]);

/**
 * Dos o mas palabras seguidas con mayuscula inicial ("Juan Pérez") o en
 * mayusculas ("MARIO SABANAGRANDE") que no sean frases de estado ni siglas.
 * Es una heuristica, y se acepta su falso positivo (un mensaje de operacion
 * omitido de mas) porque el falso negativo es un nombre en un servidor ajeno.
 */
export function pareceNombre(texto) {
  const palabras = texto.split(/[^\p{L}]+/u).filter(Boolean);
  let seguidas = 0;
  for (const palabra of palabras) {
    const plana = sinTildes(palabra);
    const inicial = /^\p{Lu}\p{Ll}+$/u.test(palabra) && palabra.length >= 2;
    const mayusculas = /^\p{Lu}{3,}$/u.test(palabra);
    const candidata = (inicial || mayusculas) && !MAYUSCULAS_PERMITIDAS.has(plana);
    seguidas = candidata ? seguidas + 1 : 0;
    if (seguidas >= 2) return true;
  }
  return false;
}

/**
 * Capa 2: un mensaje de error apto para salir. Si nombra a una persona
 * (vocabulario o forma de nombre) o tuvo que redactarse algo (quedo un
 * marcador), se reemplaza entero: lo que importa para "que fallo" ya esta en
 * el tipo y el stack.
 */
export function mensajeSeguro(texto) {
  if (typeof texto !== 'string' || !texto) return texto;
  const redactado = redactarTexto(texto);
  const plano = sinTildes(redactado);
  const habla = VOCABULARIO_SENSIBLE.some((p) => plano.includes(p));
  if (habla || redactado !== texto || pareceNombre(redactado)) {
    return `${MARCADOR} #${huella(texto)}`;
  }
  return redactado;
}

/** Deja la ruta; la query puede traer busquedas, telefonos, tokens. */
export function sinQuery(url) {
  if (typeof url !== 'string') return url;
  const corte = url.search(/[?#]/);
  return corte === -1 ? url : url.slice(0, corte);
}

/** Una ruta o URL tiene forma de ruta, no de mensaje: '/api/clientes' no
 *  habla de una persona aunque diga "clientes". */
function pareceRuta(texto) {
  return /^(?:https?:\/\/|\/)/.test(texto);
}

/**
 * Una ruta apta para salir: sin query ni fragmento, y con los segmentos
 * numericos reemplazados -- '/api/clientes/5832/' identifica a un cliente
 * tanto como su cedula, y el motor ya no deja salir id_cliente por el log.
 * Los UUID se quedan: identifican una conversacion, no a una persona.
 */
export function redactarRuta(url) {
  if (typeof url !== 'string') return url;
  return redactarTexto(sinQuery(url).replace(/\/\d{3,}(?=\/|$)/g, '/<id>'));
}

/**
 * Limpia un payload LIBRE (extra, contexts, tags, data de migas/spans,
 * atributos de logs): elimina claves prohibidas y redacta todo texto.
 */
export function limpiarObjeto(valor, profundidad = 0) {
  if (valor === null || valor === undefined) return valor;
  // Las dos capas, no solo los patrones: un texto libre dentro de `extra` o de
  // los atributos de un log puede traer un nombre sin un solo digito. Una ruta
  // es otra cosa: se limpia como ruta.
  if (typeof valor === 'string') return pareceRuta(valor) ? redactarRuta(valor) : mensajeSeguro(valor);
  if (typeof valor !== 'object') return valor;
  if (profundidad >= PROFUNDIDAD_MAXIMA) return '<profundidad>';
  if (Array.isArray(valor)) return valor.map((v) => limpiarObjeto(v, profundidad + 1));
  const salida = {};
  for (const [clave, v] of Object.entries(valor)) {
    if (CLAVES_PROHIBIDAS.has(clave.toLowerCase())) continue;
    salida[clave] = limpiarObjeto(v, profundidad + 1);
  }
  return salida;
}

function limpiarRequest(request) {
  if (!request || typeof request !== 'object') return undefined;
  const salida = {};
  if (typeof request.url === 'string') salida.url = redactarRuta(request.url);
  if (typeof request.method === 'string') salida.method = request.method;
  // cookies, headers, data y query_string: nunca.
  return salida;
}

function limpiarFrames(frames) {
  if (!Array.isArray(frames)) return frames;
  return frames.map((f) => {
    const salida = {};
    for (const k of ['filename', 'function', 'module', 'lineno', 'colno', 'in_app', 'abs_path']) {
      if (f && f[k] !== undefined) salida[k] = k === 'abs_path' || k === 'filename' ? sinQuery(f[k]) : f[k];
    }
    // `vars` (valores locales) y `context_line`/`pre_context`/`post_context`
    // (codigo fuente con literales) no viajan.
    return salida;
  });
}

/** beforeBreadcrumb: una miga, limpia. */
export function limpiarMiga(miga) {
  try {
    if (!miga || typeof miga !== 'object') return miga;
    const salida = { ...miga };
    if (typeof salida.message === 'string') salida.message = mensajeSeguro(salida.message);
    if (salida.data && typeof salida.data === 'object') {
      const data = { ...salida.data };
      for (const k of ['url', 'from', 'to']) if (typeof data[k] === 'string') data[k] = redactarRuta(data[k]);
      delete data.request_body;
      delete data.response_body;
      delete data.request_body_size;
      delete data.response_body_size;
      if (Array.isArray(data.arguments)) {
        // console.*(...): cada argumento pasa por la limpieza de payload libre.
        data.arguments = data.arguments.map((a) =>
          typeof a === 'string' ? mensajeSeguro(a) : limpiarObjeto(a)
        );
      }
      salida.data = limpiarObjeto(data);
    }
    return salida;
  } catch {
    return null;
  }
}

/** beforeSend: un evento de error, limpio. null = no sale. */
export function limpiarEvento(evento) {
  try {
    if (!evento || typeof evento !== 'object') return null;
    const salida = { ...evento };
    delete salida.user;
    delete salida.server_name;
    salida.request = limpiarRequest(salida.request);
    if (typeof salida.message === 'string') salida.message = mensajeSeguro(salida.message);
    if (salida.logentry && typeof salida.logentry === 'object') {
      salida.logentry = { ...salida.logentry };
      if (typeof salida.logentry.message === 'string') {
        salida.logentry.message = mensajeSeguro(salida.logentry.message);
      }
      delete salida.logentry.params;
    }
    if (salida.exception && Array.isArray(salida.exception.values)) {
      salida.exception = {
        ...salida.exception,
        values: salida.exception.values.map((v) => ({
          ...v,
          value: mensajeSeguro(v?.value),
          stacktrace: v?.stacktrace
            ? { ...v.stacktrace, frames: limpiarFrames(v.stacktrace.frames) }
            : v?.stacktrace,
          mechanism: v?.mechanism ? { type: v.mechanism.type, handled: v.mechanism.handled } : v?.mechanism
        }))
      };
    }
    if (Array.isArray(salida.breadcrumbs)) {
      salida.breadcrumbs = salida.breadcrumbs.map(limpiarMiga).filter(Boolean);
    }
    for (const campo of ['extra', 'tags']) {
      if (salida[campo] && typeof salida[campo] === 'object') salida[campo] = limpiarObjeto(salida[campo]);
    }
    if (salida.contexts && typeof salida.contexts === 'object') {
      const contexts = { ...salida.contexts };
      delete contexts.user;
      delete contexts.geo;
      salida.contexts = limpiarObjeto(contexts);
    }
    if (typeof salida.transaction === 'string') salida.transaction = redactarRuta(salida.transaction);
    return salida;
  } catch {
    return null;
  }
}

/** beforeSendTransaction: una traza de rendimiento, limpia. */
export function limpiarTransaccion(transaccion) {
  try {
    const salida = limpiarEvento(transaccion);
    if (!salida) return null;
    if (Array.isArray(salida.spans)) {
      salida.spans = salida.spans.map((s) => {
        const span = { ...s };
        // 'GET /api/clientes?telefono=...' es una ruta con verbo: se limpia
        // como ruta (sin query, sin ids), no como mensaje -- si no, la palabra
        // "clientes" la haria desaparecer entera.
        if (typeof span.description === 'string') span.description = redactarRuta(span.description);
        if (span.data && typeof span.data === 'object') {
          const data = { ...span.data };
          for (const k of ['url', 'http.url', 'server.address']) {
            if (typeof data[k] === 'string') data[k] = redactarRuta(data[k]);
          }
          span.data = limpiarObjeto(data);
        }
        return span;
      });
    }
    return salida;
  } catch {
    return null;
  }
}

/** beforeSendLog: un log estructurado, limpio. */
export function limpiarLog(log) {
  try {
    if (!log || typeof log !== 'object') return null;
    const salida = { ...log };
    if (typeof salida.message === 'string') salida.message = mensajeSeguro(salida.message);
    if (salida.attributes && typeof salida.attributes === 'object') {
      salida.attributes = limpiarObjeto(salida.attributes);
    }
    return salida;
  } catch {
    return null;
  }
}

/**
 * Para console.* en el cliente: un error reducido a lo que hace falta para
 * saber que fallo. Nunca el objeto entero (un Error de fetch o axios carga
 * cabeceras, cuerpos y respuestas del backend, que traen texto del cliente).
 */
export function describirError(err) {
  if (err === null || err === undefined) return { tipo: 'desconocido' };
  const salida = {
    tipo: typeof err === 'object' && typeof err.name === 'string' ? err.name : typeof err
  };
  const mensaje = typeof err === 'object' && typeof err.message === 'string' ? err.message : String(err);
  salida.mensaje = mensajeSeguro(mensaje);
  const status = err?.response?.status ?? err?.status;
  if (status !== undefined && status !== null) salida.status = status;
  if (typeof err?.code === 'string' && err.code) salida.codigo = err.code;
  return salida;
}
