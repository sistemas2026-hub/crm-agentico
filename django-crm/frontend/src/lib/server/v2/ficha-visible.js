/**
 * LA FICHA DEL CLIENTE SEGÚN QUIÉN MIRA  --  12/11/2026
 *
 * Server-only. Qué puede ver de la ficha del titular la persona de esta
 * sesión NO se decide acá: lo decide el motor, con un solo criterio
 * (nucleo/seguridad/ficha_por_area.py) -- gestión ve todo; los demás, lo que
 * declare su área; sin área, un defecto sin cédula, correo ni coordenadas.
 * Esta capa solo le dice al motor QUIÉN mira y conserva las claves que el
 * motor permite.
 *
 * Quién mira: el rol sale del JWT que verificó hooks.server.js
 * (`locals.profile.role`), nunca del navegador; el perfil, de la lista de la
 * organización resuelta por la sesión. El motor no confía en un área que le
 * mande nadie: la lee de su base por el perfil.
 *
 * Fail-closed: si el motor no contesta la visibilidad, la ficha llega SIN
 * datos personales y con la marca `_sinCriterio`, para que la pantalla diga
 * por qué y no muestre un vacío que parezca "el cliente no tiene cédula".
 */
/** El rol de quien mira, del JWT verificado (la misma lectura que
 *  `rolDeSesion` de operadores.js, sin arrastrar el cliente HTTP del CRM). */
const rolDeSesion = (/** @type {any} */ locals) =>
  String(locals?.profile?.role ?? 'USER').toUpperCase();

/**
 * Los parámetros con los que una ruta del motor sabe quién mira.
 * @param {any} locals
 * @param {string | null | undefined} perfil Profile.id de quien mira
 * @returns {Record<string, string>}
 */
export function quienMira(locals, perfil) {
  /** @type {Record<string, string>} */
  const p = { rol: rolDeSesion(locals) };
  if (perfil) p.perfil = String(perfil);
  return p;
}

/**
 * Qué claves de la ficha puede recibir quien mira, preguntado al motor.
 * Null si no contesta o contesta algo que no tiene la forma esperada.
 *
 * @param {typeof globalThis.fetch} fetch
 * @param {{ base: string, tenant: string, locals: any, perfil?: string | null, headers?: Record<string, string> }} p
 * @returns {Promise<{ campos: string[], ocultos: string[], criterio: string } | null>}
 */
export async function leerVisibilidad(fetch, { base, tenant, locals, perfil, headers = {} }) {
  try {
    const qs = new URLSearchParams({ tenant, ...quienMira(locals, perfil) });
    const r = await fetch(`${base}/ficha-cliente/visibilidad?${qs}`, {
      headers,
      signal: AbortSignal.timeout(10000)
    });
    if (!r.ok) return null;
    const d = await r.json();
    return Array.isArray(d?.campos) && Array.isArray(d?.ocultos) ? d : null;
  } catch {
    return null;
  }
}

/**
 * La ficha del titular, con solo lo que quien mira puede ver. Pura.
 *
 * Misma forma que la que entrega el motor en la Bandeja: los campos visibles
 * más `_ocultos`. Sin visibilidad (el motor no la dio) no pasa ningún dato:
 * `{ _ocultos: [], _sinCriterio: true }`.
 *
 * @param {any} cliente
 * @param {{ campos: string[], ocultos: string[] } | null} visibilidad
 * @returns {any}
 */
export function filtrarFicha(cliente, visibilidad) {
  if (!cliente || typeof cliente !== 'object') return cliente ?? null;
  if (!visibilidad) return { _ocultos: [], _sinCriterio: true };
  const permitidas = new Set(visibilidad.campos);
  /** @type {Record<string, any>} */
  const salida = {};
  for (const [k, v] of Object.entries(cliente)) {
    if (permitidas.has(k)) salida[k] = v;
  }
  salida._ocultos = [...visibilidad.ocultos];
  return salida;
}

/**
 * El contexto técnico del ticket (`/conversaciones/por-caso`), con la ficha
 * del titular (`contexto.cliente`) filtrada. Lo demás -- enlaces, equipo,
 * identidad -- no es la ficha y pasa igual. Pura.
 *
 * @param {any} contexto
 * @param {{ campos: string[], ocultos: string[] } | null} visibilidad
 */
export function contextoParaQuienMira(contexto, visibilidad) {
  if (!contexto || typeof contexto !== 'object' || !('cliente' in contexto)) return contexto;
  return { ...contexto, cliente: filtrarFicha(contexto.cliente, visibilidad) };
}
