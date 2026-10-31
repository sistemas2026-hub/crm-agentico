import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * "Nuevo ticket" tambien en WispHub (26/10/2026).
 *
 * La pantalla no habla con WispHub: le pide al motor, que tiene la credencial
 * y decide. Crear y atar el caso al ticket ocurre del otro lado y en un solo
 * paso (nucleo/seguimiento/ticket_desde_dexter.py): el numero de ticket lo lee
 * el motor de la respuesta de WispHub, nunca lo manda el navegador.
 *
 * Las tres degradan sin romper la pantalla: sin motor, el formulario no ofrece
 * WispHub y el ticket queda solo en Dexter, que es un estado valido.
 */

/** Lo que el motor contesta cuando no se creo, dicho para quien llena el formulario. */
export const MOTIVOS = /** @type {Record<string, string>} */ ({
  ASUNTO_NO_PERMITIDO: 'Ese asunto no está habilitado para crear en WispHub.',
  SERVICIO_INVALIDO: 'El número de servicio no es válido: van solo dígitos.',
  SERVICIO_NO_EXISTE: 'Ese número de servicio no existe en WispHub.',
  FALTA_DESCRIPCION: 'Para crearlo en WispHub hace falta contar qué pasó.',
  FALTA_AUTOR: 'No se pudo saber quién lo crea. Volvé a iniciar sesión.',
  NO_CONFIGURADO: 'Crear tickets en WispHub no está configurado para esta empresa.',
  ISP_NO_CONTESTA: 'WispHub no respondió.',
  NO_SE_CREO: 'WispHub no aceptó el ticket.',
  SIN_ID_DE_TICKET: 'WispHub no devolvió el número del ticket.',
  ADJUNTO_INVALIDO: 'El archivo no se pudo leer.',
  ADJUNTO_MUY_GRANDE: 'El archivo pesa más de 25 MB.',
  BUSQUEDA_CORTA: 'Escribí al menos 3 letras o números.',
  SIN_BUSQUEDA_POR_NOMBRE: 'Para esta empresa se busca por número de servicio o cédula.',
  INCIERTO:
    'No se pudo confirmar si quedó creado en WispHub. Si en unos minutos el ticket muestra «WispHub #…» arriba, quedó creado; si no, avisá a un administrador antes de crearlo de nuevo.'
});

/** @param {App.Locals} locals @param {typeof globalThis.fetch} fetch */
async function destino(locals, fetch) {
  const base = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  return base && tenant ? { base, tenant } : null;
}

/**
 * Los asuntos con que se puede abrir el ticket en WispHub. [] = no se ofrece.
 * Primero los frecuentes ('frecuente'), con su área; después el resto del
 * catálogo de WispHub (28/10/2026).
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @returns {Promise<{asunto: string, area: string, frecuente?: boolean}[]>}
 */
export async function leerAsuntosWispHub(locals, fetch) {
  const d = await destino(locals, fetch);
  if (!d) return [];
  try {
    const r = await fetch(
      `${d.base}/tickets-desde-dexter/asuntos?tenant=${encodeURIComponent(d.tenant)}`,
      //  8 s: la primera vez el motor lee el catalogo de WispHub (se guarda una hora).
      { headers: headersMotor(), signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) return [];
    const cuerpo = await r.json();
    return Array.isArray(cuerpo?.asuntos) ? cuerpo.asuntos : [];
  } catch {
    return [];
  }
}

/**
 * El cliente por número de servicio, cédula o nombre (28/10/2026). De cada
 * uno llega solo servicio, nombre y estado: el motor no manda más.
 *
 * 'cargando' = el motor está armando la lista de clientes para buscar por
 * nombre (la primera vez tarda cerca de un minuto); la pantalla reintenta.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {string} texto
 * @returns {Promise<{ok: true, resultados: {servicio: string, nombre: string, estado: string}[],
 *   mas: boolean, cargando: boolean} | {ok: false, motivo: string}>}
 */
export async function buscarClientes(locals, fetch, texto) {
  const q = String(texto ?? '').trim();
  if (q.length < 3) return { ok: false, motivo: MOTIVOS.BUSQUEDA_CORTA };
  const d = await destino(locals, fetch);
  if (!d) return { ok: false, motivo: MOTIVOS.NO_CONFIGURADO };
  try {
    const r = await fetch(
      `${d.base}/clientes/buscar?tenant=${encodeURIComponent(d.tenant)}&q=${encodeURIComponent(q)}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(15000) }
    );
    const cuerpo = await r.json().catch(() => ({}));
    if (!r.ok) return { ok: false, motivo: MOTIVOS[cuerpo?.error] ?? MOTIVOS.ISP_NO_CONTESTA };
    const resultados = (Array.isArray(cuerpo?.resultados) ? cuerpo.resultados : []).map(
      (/** @type {any} */ c) => ({
        servicio: String(c.servicio ?? ''),
        nombre: c.nombre ?? '',
        estado: c.estado ?? ''
      })
    );
    return { ok: true, resultados, mas: cuerpo?.mas === true, cargando: cuerpo?.cargando === true };
  } catch {
    return { ok: false, motivo: MOTIVOS.ISP_NO_CONTESTA };
  }
}

/**
 * Crea en WispHub el ticket de un caso recien creado, y lo ata.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {string} casoId
 * 'archivo' (27/10/2026) va al ticket ya creado, del otro lado. 'adjunto' en
 * la respuesta: true si llego, false si el ticket se creo pero el archivo no,
 * ausente si no se mando ninguno.
 *
 * @param {{servicio: string, asunto: string, descripcion: string, prioridad?: string,
 *   archivo?: {nombre: string, tipo: string, base64: string}}} datos
 * @returns {Promise<{ok: true, idTicket: string, vinculado: boolean, adjunto?: boolean} | {ok: false, motivo: string}>}
 */
export async function crearEnWispHub(locals, fetch, casoId, datos) {
  const d = await destino(locals, fetch);
  if (!d) return { ok: false, motivo: MOTIVOS.NO_CONFIGURADO };
  try {
    const r = await fetch(`${d.base}/casos/${encodeURIComponent(casoId)}/ticket-operativo`, {
      method: 'POST',
      headers: { ...headersMotor(), 'content-type': 'application/json' },
      body: JSON.stringify({
        tenant: d.tenant,
        servicio: datos.servicio,
        asunto: datos.asunto,
        descripcion: datos.descripcion,
        ...(datos.prioridad ? { prioridad: datos.prioridad } : {}),
        ...(datos.archivo ? { archivo: datos.archivo } : {}),
        ...autorDeSesion(locals)
      }),
      //  Con archivo es una subida mas a WispHub, de hasta 25 MB.
      signal: AbortSignal.timeout(datos.archivo ? 90000 : 30000)
    });
    const cuerpo = await r.json().catch(() => ({}));
    if (r.ok && cuerpo?.id_ticket) {
      return {
        ok: true,
        idTicket: String(cuerpo.id_ticket),
        vinculado: cuerpo.vinculado === true,
        ...(typeof cuerpo.adjunto === 'boolean' ? { adjunto: cuerpo.adjunto } : {})
      };
    }
    return { ok: false, motivo: MOTIVOS[cuerpo?.error] ?? MOTIVOS.NO_SE_CREO };
  } catch {
    return { ok: false, motivo: MOTIVOS.INCIERTO };
  }
}
