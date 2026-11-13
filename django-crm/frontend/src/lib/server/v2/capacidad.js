/**
 * El tablero de capacidad (30/10/2026, PRD §2 y §8.17 Ola 1): cuánto trabajo
 * le resolvió Dexter a la empresa, con sus contrapesos. Los números los
 * calcula el motor (nucleo/observabilidad/capacidad.py); acá solo se piden y
 * se pasan tal cual, con los mismos nombres. Ningún dato de un cliente.
 *
 * Server-only. No lanza: si el motor no contesta, devuelve el error.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/** Los períodos que ofrece la pantalla. Otro valor vuelve al de en medio. */
export const PERIODOS = [7, 30, 90];

/**
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {number} dias
 * @returns {Promise<{ tablero: any | null, error?: string }>}
 */
export async function leerTableroCapacidad(locals, fetch, dias, personasEquipo = null) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return { tablero: null, error: 'Asistente no configurado para esta empresa.' };
  const q = new URLSearchParams({ tenant: cfg.tenant, dias: String(dias) });
  //  Solo se usa si la empresa no declaró el número (12/11/2026): lo
  //  declarado manda, esto lo pre-llena.
  if (personasEquipo) q.set('personas_equipo', String(personasEquipo));
  try {
    const resp = await fetch(`${cfg.baseUrl}/reportes/capacidad?${q}`, {
      headers: headersMotor(),
      signal: AbortSignal.timeout(20000)
    });
    const datos = await resp.json();
    if (!resp.ok) return { tablero: null, error: datos?.error || 'No se pudo calcular el tablero.' };
    return { tablero: datos };
  } catch {
    return { tablero: null, error: 'No se pudo contactar al asistente.' };
  }
}

/**
 * Cuántas personas ACTIVAS del equipo tienen un área de atención (12/11/2026).
 *
 * `personas_del_equipo` se declaraba a mano aunque /team ya lo sabe: las
 * personas activas del CRM cruzadas con el área que cada una tiene en el
 * asistente (`/agentes/asignaciones`). Se cruzan las dos porque ninguna sola
 * alcanza: el CRM no sabe quién atiende clientes, y el asistente no sabe quién
 * se desactivó (el traspaso al desactivar le quita el área, pero no lanza si
 * falla).
 *
 * `null` si no se pudo saber — nunca 0: un cero dividiría «casos por persona»
 * por nada y diría que el equipo no existe. No lanza.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {(e: { cookies: any }) => Promise<any>} listarEquipo `team.js::listTeam`
 * @param {any} cookies
 * @returns {Promise<number | null>}
 */
export async function contarPersonasDelEquipo(locals, fetch, listarEquipo, cookies) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const [equipo, resp] = await Promise.all([
      listarEquipo({ cookies }),
      fetch(`${cfg.baseUrl}/agentes/asignaciones?tenant=${encodeURIComponent(cfg.tenant)}`, {
        headers: headersMotor()
      })
    ]);
    if (!equipo || equipo.forbidden || !resp.ok) return null;
    const { areas_por_persona: areas = {} } = await resp.json();
    const n = (equipo.active ?? []).filter(
      (/** @type {any} */ m) => typeof areas[m.id] === 'string' && areas[m.id].trim() !== ''
    ).length;
    return n > 0 ? n : null;
  } catch {
    return null;
  }
}

/**
 * Lo que declara la empresa para que el tablero pueda traducir a minutos y a
 * casos por persona. `null` = sin declarar: el tablero muestra "—" con el
 * motivo, nunca un número supuesto. Lanza si el motor rechaza.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {{ minutos_por_conversacion: number|null, minutos_por_visita: number|null,
 *           personas_del_equipo: number|null }} valores
 */
export async function guardarDeclaracionCapacidad(locals, fetch, valores) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado para esta empresa.');
  const resp = await fetch(`${cfg.baseUrl}/configuracion/capacidad`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, ...valores })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'El asistente rechazó el cambio.');
  return datos;
}

/**
 * La autonomía ganada (31/10/2026, PRD §2 y §8.17 Ola 3): qué acciones que hoy
 * aprueba una persona podrían hacerse solas en esta empresa, con su evidencia
 * y lo que les falta. Lo calcula el motor (nucleo/seguridad/autonomia_ganada.py);
 * acá solo se pide. No promueve nada. No lanza.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @returns {Promise<{ autonomia: any | null, error?: string }>}
 */
export async function leerAutonomiaGanada(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return { autonomia: null, error: 'Asistente no configurado para esta empresa.' };
  const q = new URLSearchParams({ tenant: cfg.tenant });
  try {
    const resp = await fetch(`${cfg.baseUrl}/reportes/autonomia-ganada?${q}`, {
      headers: headersMotor(),
      signal: AbortSignal.timeout(20000)
    });
    const datos = await resp.json();
    if (!resp.ok) return { autonomia: null, error: datos?.error || 'No se pudo calcular la autonomía ganada.' };
    return { autonomia: datos };
  } catch {
    return { autonomia: null, error: 'No se pudo contactar al asistente.' };
  }
}

/**
 * Darle o quitarle autonomía a una acción (31/10/2026, PRD §2, Fase B). El
 * autor sale de la SESIÓN, nunca del navegador. Promover: el motor vuelve a
 * medir la evidencia y contesta 409 con lo que falta si no alcanza. Lanza un
 * error con `.codigo` y `.faltan` si el motor rechaza.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {'promover' | 'retirar'} que
 * @param {{ accion: string, motivo?: string }} datos
 */
export async function cambiarAutonomia(locals, fetch, que, datos) {
  const { autorDeSesion } = await import('./autor.js');
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw Object.assign(new Error('Asistente no configurado para esta empresa.'), { codigo: 'NO_CONFIGURADO' });
  const resp = await fetch(`${cfg.baseUrl}/autonomia-ganada/${que}`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    //  El rol también sale de la SESIÓN: el motor vuelve a exigir ADMIN.
    body: JSON.stringify({ tenant: cfg.tenant, ...datos, ...autorDeSesion(locals),
      autor_rol: locals?.profile?.role ?? '' })
  });
  const cuerpo = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw Object.assign(new Error(cuerpo.error || 'El asistente rechazó el cambio.'),
      { codigo: cuerpo.error || 'RECHAZADO', faltan: cuerpo.faltan ?? [] });
  }
  return cuerpo;
}

/**
 * Si una accion es critica en esta empresa (04/11/2026, PRD §2). Solo ADMIN:
 * el autor y su rol salen de la SESION y el motor los vuelve a exigir. El
 * esquema rechaza declarar no critica una accion sin las garantias en codigo.
 * Lanza un error con `.codigo` si el motor rechaza.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {{ accion: string, critica: boolean }} datos
 */
export async function cambiarCriticidad(locals, fetch, datos) {
  const { autorDeSesion } = await import('./autor.js');
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw Object.assign(new Error('Asistente no configurado para esta empresa.'), { codigo: 'NO_CONFIGURADO' });
  const resp = await fetch(`${cfg.baseUrl}/agentes/herramientas/${encodeURIComponent(datos.accion)}/critica`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, critica: datos.critica, ...autorDeSesion(locals),
      autor_rol: locals?.profile?.role ?? '' })
  });
  const cuerpo = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw Object.assign(new Error(cuerpo.error || 'El asistente rechazó el cambio.'),
      { codigo: cuerpo.error || 'RECHAZADO' });
  }
  return cuerpo;
}
