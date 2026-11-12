/**
 * Global search for the ⌘K palette, the wiring behind /api/search.
 *
 * Server-only. Two sources, read in parallel and each with its own deadline:
 *
 *   CRM     `GET /search/`, org-scoped by the JWT (each type already filtered
 *           to what the caller may open). Since 12/11/2026 it also returns
 *           installation requests (`solicitud`, management roles only) and
 *           field orders (`orden`, with the same visibility as the order).
 *   motor   the Bandeja's own message search (`buscarEnMensajes`), so the
 *           palette reaches CONVERSATIONS. The tenant comes from the session,
 *           never from the browser (`destinoDelAsistente`).
 *
 * LO QUE BUSCA EL MOTOR ES EL TEXTO DE LOS MENSAJES, no el nombre ni el
 * teléfono del chat: `GET /conversaciones/buscar` hace ILIKE sobre
 * `messages` (nucleo/persistencia/db.py::buscar_en_mensajes). Un nombre o un
 * número aparecen solo si alguien los escribió en la conversación. Buscar por
 * la identidad del chat pide una ruta nueva del motor; no se simula acá
 * bajando la cola entera (la consulta más cara de la portada) en cada tecla.
 *
 * UNA FUENTE QUE FALLA O SE DEMORA NO TAPA A LA OTRA. Cada una tiene
 * PLAZO_FUENTE_MS; la que no llega se nombra en `incompletas` y la paleta lo
 * dice, en vez de afirmar «nada coincide».
 *
 * PRIVACIDAD: `q` puede ser un teléfono o un documento. No va a ningún log.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { conPlazo } from './plazo.js';
import { buscarEnMensajes, BUSQUEDA_MINIMO, normalizarBusqueda } from './busqueda-mensajes.js';

/** Cuánto se espera a cada fuente. Es una búsqueda mientras se escribe: más
 *  que esto y la persona ya tecleó otra cosa. */
export const PLAZO_FUENTE_MS = 4000;
/** Conversaciones distintas que se muestran como máximo. */
const CONVERSACIONES_MAX = 6;

/** Backend `type` → palette group label + detail route. */
const MAP = {
  lead: { kind: 'Prospectos', href: (/** @type {any} */ r) => `/leads/${r.id}` },
  deal: { kind: 'Negociaciones', href: (/** @type {any} */ r) => `/pipeline/${r.id}` },
  account: { kind: 'Cuentas', href: (/** @type {any} */ r) => `/accounts/${r.id}` },
  contact: { kind: 'Contactos', href: (/** @type {any} */ r) => `/contacts/${r.id}` },
  ticket: { kind: 'Tickets', href: (/** @type {any} */ r) => `/tickets/${r.id}` },
  invoice: { kind: 'Facturas', href: (/** @type {any} */ r) => `/invoices/${r.id}` },
  solution: { kind: 'Base de conocimiento', href: (/** @type {any} */ r) => `/solutions/${r.id}` },
  // La bandeja de Instalaciones filtra por estado; la solicitud se ve ahí.
  solicitud: {
    kind: 'Instalaciones',
    href: (/** @type {any} */ r) =>
      r.estado ? `/instalaciones?estado=${encodeURIComponent(r.estado)}` : '/instalaciones'
  },
  orden: { kind: 'Órdenes', href: (/** @type {any} */ r) => `/ordenes/${r.id}` }
};

/**
 * Lo del CRM, con la forma de la paleta. Una orden con id de servicio suma
 * además su cliente (`/clientes/<id_servicio>`), una vez por cliente.
 *
 * @param {any[]} filas
 */
export function deCrm(filas) {
  /** @type {any[]} */
  const salida = [];
  const clientes = new Set();
  for (const r of filas) {
    const m = MAP[/** @type {keyof typeof MAP} */ (r?.type)];
    if (!m) continue;
    salida.push({ kind: m.kind, id: `${r.type}-${r.id}`, title: r.title, meta: r.subtitle || '', href: m.href(r) });
    if (r.type === 'orden' && r.id_servicio && !clientes.has(r.id_servicio)) {
      clientes.add(r.id_servicio);
      salida.push({
        kind: 'Clientes',
        id: `cliente-${r.id_servicio}`,
        title: String(r.title || '').replace(/^OT-\d+\s*·\s*/, '') || `Servicio ${r.id_servicio}`,
        meta: `Servicio ${r.id_servicio}`,
        href: `/clientes/${encodeURIComponent(r.id_servicio)}`
      });
    }
  }
  return salida;
}

/**
 * Los mensajes que encontró el motor, uno por conversación.
 *
 * @param {any[]} resultados
 */
export function deConversaciones(resultados) {
  /** @type {any[]} */
  const salida = [];
  const vistas = new Set();
  for (const r of resultados) {
    if (!r?.conversation_id || vistas.has(r.conversation_id)) continue;
    vistas.add(r.conversation_id);
    salida.push({
      kind: 'Conversaciones',
      id: `conv-${r.conversation_id}`,
      title: r.nombre_cliente || r.usuario_externo || 'Conversación',
      meta: r.fragmento || '',
      href: `/conversaciones/${encodeURIComponent(r.conversation_id)}`
    });
    if (salida.length >= CONVERSACIONES_MAX) break;
  }
  return salida;
}

/**
 * Org-scoped search, shaped for the palette (`{ kind, id, title, meta, href }`).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies, locals?: App.Locals,
 *           fetch?: typeof globalThis.fetch, signal?: AbortSignal }} event
 * @param {string} q
 * @returns {Promise<{ results: any[], incompletas: string[] }>}
 */
export async function search({ cookies, locals, fetch, signal }, q) {
  const query = (q || '').trim();
  if (query.length < 2) return { results: [], incompletas: [] };

  const texto = normalizarBusqueda(query);
  const conMotor = Boolean(locals && fetch) && texto.length >= BUSQUEDA_MINIMO;

  const [crm, motor] = await Promise.all([
    conPlazo(apiRequest(`/search/?q=${encodeURIComponent(query)}`, {}, { cookies }), PLAZO_FUENTE_MS),
    conMotor
      ? conPlazo(
          buscarEnMensajes(/** @type {App.Locals} */ (locals), /** @type {any} */ (fetch), texto, {
            signal,
            vista: 'operativo'
          }),
          PLAZO_FUENTE_MS
        )
      : Promise.resolve(undefined)
  ]);

  /** @type {string[]} */
  const incompletas = [];
  if (crm == null) incompletas.push('el CRM');
  if (conMotor && motor == null) incompletas.push('las conversaciones');

  const results = [
    ...(motor ? deConversaciones(motor.resultados) : []),
    ...(crm ? deCrm(crm.results || []) : [])
  ];
  return { results, incompletas };
}
