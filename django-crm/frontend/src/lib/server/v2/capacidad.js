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
export async function leerTableroCapacidad(locals, fetch, dias) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return { tablero: null, error: 'Asistente no configurado para esta empresa.' };
  const q = new URLSearchParams({ tenant: cfg.tenant, dias: String(dias) });
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
    body: JSON.stringify({ tenant: cfg.tenant, ...datos, ...autorDeSesion(locals) })
  });
  const cuerpo = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw Object.assign(new Error(cuerpo.error || 'El asistente rechazó el cambio.'),
      { codigo: cuerpo.error || 'RECHAZADO', faltan: cuerpo.faltan ?? [] });
  }
  return cuerpo;
}
