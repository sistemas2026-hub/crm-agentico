/**
 * BUSCAR EN EL CONTENIDO DE LOS MENSAJES  --  11/11/2026
 *
 * Server-only. El buscador de la Bandeja filtraba lo YA cargado y del mensaje
 * solo miraba el último de cada conversación; esto le pregunta al motor
 * (`GET /conversaciones/buscar`), que busca en todos los mensajes de la
 * empresa acotado por organización. El tenant sale de la sesión, nunca del
 * navegador: quien busca no elige en qué empresa.
 *
 * QUÉ PASA DE LARGO Y QUÉ NO
 * Se copian los campos que la pantalla usa, con el MISMO nombre que trae el
 * motor. No es descuido: el 29/09/2026 `requiere_noc` viajaba bien del backend
 * y esta capa lo dejaba caer, y la bandeja del NOC quedó vacía para siempre.
 * Renombrar acá es abrir la misma puerta; la prueba de esta función afirma
 * que cada campo llega.
 *
 * PRIVACIDAD: `q` es texto de un cliente. Va en la query string del motor,
 * que su registro de acceso no escribe, y NO va a ningún console de acá.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

export const BUSQUEDA_MINIMO = 3;
export const BUSQUEDA_MAXIMO = 100;
/** Cuánto se espera al motor. Es una búsqueda mientras se escribe: si tarda
 *  más que esto, la persona ya escribió otra cosa. */
export const PLAZO_BUSQUEDA_MS = 8000;

/** Las vistas de canales de la cola. La base filtra por ellas ANTES de cortar
 *  en 30 (11/11/2026, auditoría H2); el motor rechaza cualquier otra. */
export const VISTAS_BUSQUEDA = Object.freeze(['operativo', 'pruebas', 'todos']);

/** `q` con los espacios normalizados, que es lo que mide el rango. */
export const normalizarBusqueda = (/** @type {unknown} */ q) =>
  String(q ?? '').split(/\s+/).filter(Boolean).join(' ');

/**
 * Los mensajes que contienen `q`, como los devuelve el motor.
 *
 * Lanza si el motor no está, no contesta a tiempo o rechaza: quien llama
 * decide qué decir. Con `signal`, el pedido al motor se corta cuando el
 * navegador abandona el suyo (otra tecla).
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {string} q
 * @param {{ signal?: AbortSignal, vista?: string }} [opciones]
 * @returns {Promise<{ resultados: any[], tope: number | null }>}
 */
export async function buscarEnMensajes(locals, fetch, q, opciones = {}) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  // AbortController + setTimeout y no AbortSignal.timeout: el segundo no
  // respeta los relojes falsos de las pruebas, y la prueba pasaría por el
  // camino equivocado tardando lo real.
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), PLAZO_BUSQUEDA_MS);
  const alAbandonar = () => control.abort();
  opciones.signal?.addEventListener('abort', alAbandonar);
  try {
    const url =
      `${cfg.baseUrl}/conversaciones/buscar?tenant=${encodeURIComponent(cfg.tenant)}` +
      `&q=${encodeURIComponent(q)}` +
      `&vista=${encodeURIComponent(opciones.vista ?? 'todos')}`;
    const resp = await fetch(url, { headers: headersMotor(), signal: control.signal });
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(datos?.error || 'El asistente no pudo buscar en los mensajes.');
    const resultados = (Array.isArray(datos?.resultados) ? datos.resultados : []).map(
      (/** @type {any} */ r) => ({
        conversation_id: r.conversation_id,
        mensaje_id: r.mensaje_id,
        rol: r.rol,
        es_nota: r.es_nota === true,
        creado_en: r.creado_en,
        fragmento: r.fragmento ?? '',
        nombre_cliente: r.nombre_cliente ?? null,
        usuario_externo: r.usuario_externo ?? null,
        estado: r.estado ?? null,
        canal_operativo: r.canal_operativo
      })
    );
    return { resultados, tope: Number.isFinite(datos?.tope) ? datos.tope : null };
  } finally {
    clearTimeout(reloj);
    opciones.signal?.removeEventListener('abort', alAbandonar);
  }
}
