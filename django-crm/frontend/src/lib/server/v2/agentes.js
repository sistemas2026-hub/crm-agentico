import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { destinoDelAsistente } from '$lib/server/v2/tenant.js';

/**
 * LO QUE LAS PAGINAS DE AGENTES LE PIDEN AL MOTOR  --  13/11/2026
 *
 * Lecturas que NUNCA rechazan: cada una devuelve null (o la lista vacia) si
 * el motor no responde, y la pagina se ve sin ese dato. Que falle la
 * bitacora no puede tumbar la ficha del agente. Las escrituras (pausar,
 * restaurar) SI devuelven el error, para decirlo.
 *
 * El tenant sale de la SESION (destinoDelAsistente), nunca del navegador.
 * Las respuestas viajan enteras y con los nombres del motor (CLAUDE.md §6).
 */

/** @param {any} locals @param {typeof fetch} fetch */
export async function destino(locals, fetch) {
  return destinoDelAsistente(locals, fetch);
}

/**
 * GET al motor que no rechaza. null si no hay destino, si falla o si no es 2xx.
 * @param {{baseUrl: string, tenant: string} | null} cfg
 * @param {typeof fetch} fetch @param {string} ruta @param {Record<string, string|number>} [q]
 */
async function leer(cfg, fetch, ruta, q = {}) {
  if (!cfg) return null;
  const params = new URLSearchParams({ tenant: cfg.tenant, ...Object.fromEntries(
    Object.entries(q).map(([k, v]) => [k, String(v)])) });
  try {
    const resp = await fetch(`${cfg.baseUrl}${ruta}?${params}`, { headers: headersMotor() });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/** Desempeno por agente (GET /reportes/agentes). */
export const leerDesempeno = (/** @type {any} */ cfg, /** @type {any} */ fetch, dias = 30) =>
  leer(cfg, fetch, '/reportes/agentes', { dias });

/** Lo que un agente cambio en el mundo real. */
export const leerBitacora = (/** @type {any} */ cfg, /** @type {any} */ fetch, /** @type {string} */ nombre, dias = 30) =>
  leer(cfg, fetch, `/agentes/${encodeURIComponent(nombre)}/bitacora`, { dias });

/** Los cambios de un agente, version a version. */
export const leerHistorial = (/** @type {any} */ cfg, /** @type {any} */ fetch, /** @type {string} */ nombre) =>
  leer(cfg, fetch, `/agentes/${encodeURIComponent(nombre)}/historial`);

/** Huecos por rol (GET /habilidades/huecos), agrupados. */
export async function leerHuecosPorRol(/** @type {any} */ cfg, /** @type {any} */ fetch, dias = 14) {
  const datos = await leer(cfg, fetch, '/habilidades/huecos', { dias });
  /** @type {Record<string, any[]>} */
  const por = {};
  for (const h of datos?.huecos ?? []) {
    if (h?.rol) (por[h.rol] ??= []).push(h);
  }
  return por;
}

/**
 * Escritura al motor: devuelve {ok, datos} o {ok: false, error, status}.
 * @param {any} cfg @param {typeof fetch} fetch @param {string} metodo @param {string} ruta @param {any} cuerpo
 */
async function escribir(cfg, fetch, metodo, ruta, cuerpo) {
  if (!cfg) return { ok: false, status: 500, error: 'Asistente no configurado.' };
  try {
    const resp = await fetch(`${cfg.baseUrl}${ruta}`, {
      method: metodo,
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ ...cuerpo, tenant: cfg.tenant })
    });
    const datos = await resp.json().catch(() => ({}));
    if (!resp.ok) return { ok: false, status: resp.status, error: datos?.error || 'El asistente no lo aceptó.' };
    return { ok: true, datos };
  } catch (/** @type {any} */ e) {
    return { ok: false, status: 502, error: e?.message || 'No se pudo contactar al asistente.' };
  }
}

//  'autor' (13/11/2026): quien lo hace, de la SESION (autorDeSesion), para que
//  la version nueva del historial diga quien la hizo. El motor solo lo anota.

/** @param {any} cfg @param {typeof fetch} fetch @param {string} nombre @param {boolean} pausado @param {string} [autor] */
export const pausarAgente = (cfg, fetch, nombre, pausado, autor = '') =>
  escribir(cfg, fetch, 'PUT', `/agentes/${encodeURIComponent(nombre)}/pausa`, { pausado, ...(autor ? { autor } : {}) });

/** @param {any} cfg @param {typeof fetch} fetch @param {string} nombre @param {number} version @param {string} [autor] */
export const restaurarAgente = (cfg, fetch, nombre, version, autor = '') =>
  escribir(cfg, fetch, 'POST', `/agentes/${encodeURIComponent(nombre)}/restaurar`, { version, ...(autor ? { autor } : {}) });
