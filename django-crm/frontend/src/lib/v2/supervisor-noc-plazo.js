/**
 * EL PLAZO COMO EJE DE LA BANDEJA  --  01/11/2026
 *
 * La bandeja del Supervisor se ordenaba por una prioridad 0-99 que había que
 * interpretar. Quien entra a la pantalla quiere saber otra cosa primero: qué ya
 * se pasó de la hora y qué está por pasarse. Estas funciones agrupan por el
 * estado de SLA que YA calcula el backend (`sla_estado`): no se recalcula nada
 * acá, solo se ordena y se dice en palabras.
 *
 * Viven aparte de supervisor-noc-tablero.js, que ya pasa las mil líneas, y por
 * la misma razón que él: el titular y los grupos tienen casos borde --la
 * bandeja caída, el singular, lo que no corre reloj-- que no se pueden
 * ejercitar sin montar el componente.
 */

import { celdaDeSla } from './supervisor-noc-tablero.js';

/** Los cuatro grupos, en el orden en que se leen. */
export const GRUPOS_DE_PLAZO = [
  { clave: 'vencido', titulo: 'Plazo vencido', tono: 'critico' },
  { clave: 'pronto', titulo: 'Vencen pronto', tono: 'alerta' },
  { clave: 'plazo', titulo: 'En plazo', tono: 'neutro' },
  { clave: 'sin', titulo: 'Sin plazo', tono: 'neutro' }
];

/**
 * A qué grupo va una propuesta según su `sla_estado`.
 *
 * Todo lo que no corre reloj --orden terminada, tipo sin plazo, datos
 * insuficientes, propuesta que no cuelga de una orden-- va a «sin plazo», y no a
 * «en plazo»: estar a tiempo es una afirmación que alguien tiene que haber
 * medido.
 *
 * @param {string | null | undefined} estado
 */
export function grupoDePlazo(estado) {
  if (estado === 'VENCIDA') return 'vencido';
  if (estado === 'VENCE_PRONTO') return 'pronto';
  if (estado === 'A_TIEMPO') return 'plazo';
  return 'sin';
}

/**
 * Las filas repartidas en sus grupos, sin los vacíos. Dentro de cada grupo se
 * respeta el orden que ya traen: la bandeja llega ordenada por prioridad, y
 * reordenar por otra regla acá sería una segunda regla que nadie ve.
 *
 * @param {any[] | null | undefined} filas
 */
export function agruparPorPlazo(filas) {
  if (!Array.isArray(filas)) return [];
  return GRUPOS_DE_PLAZO.map((g) => ({
    ...g,
    filas: filas.filter((f) => grupoDePlazo(f?.sla_estado) === g.clave)
  })).filter((g) => g.filas.length > 0);
}

/**
 * Cuántas hay en cada grupo, con la MISMA regla que agrupa. Sin lista devuelve
 * null y no ceros: una bandeja que no se pudo leer no tiene "cero vencidas".
 *
 * @param {any[] | null | undefined} filas
 */
export function cuentaPorPlazo(filas) {
  if (!Array.isArray(filas)) return null;
  /** @type {Record<string, number>} */
  const cuenta = { vencido: 0, pronto: 0, plazo: 0, sin: 0 };
  for (const f of filas) cuenta[grupoDePlazo(f?.sla_estado)] += 1;
  return cuenta;
}

/** @param {number} m */
function duracion(m) {
  const d = Math.floor(m / 1440);
  const h = Math.floor((m % 1440) / 60);
  const min = Math.round(m % 60);
  if (d > 0) return h > 0 ? `${d} d ${h} h` : `${d} d`;
  if (h > 0) return min > 0 ? `${h} h ${min} min` : `${h} h`;
  return `${min} min`;
}

/**
 * El plazo en palabras, para la primera columna de la fila.
 *
 * Sin minutos no se inventa una duración: se dice el estado y nada más. Lo que
 * no corre reloj conserva el porqué que ya explicaba `celdaDeSla`.
 *
 * @param {string | null | undefined} estado
 * @param {number | null | undefined} minutos
 */
export function textoDePlazo(estado, minutos) {
  const hay = typeof minutos === 'number' && Number.isFinite(minutos);
  switch (estado) {
    case 'VENCIDA':
      return { texto: hay ? `Venció hace ${duracion(minutos)}` : 'Vencido', detalle: '', tono: 'critico' };
    case 'VENCE_PRONTO':
      return { texto: hay ? `Vence en ${duracion(minutos)}` : 'Vence pronto', detalle: '', tono: 'alerta' };
    case 'A_TIEMPO':
      return { texto: hay ? `Quedan ${duracion(minutos)}` : 'A tiempo', detalle: '', tono: 'neutro' };
    default: {
      const c = celdaDeSla(estado, minutos);
      return { texto: c.texto, detalle: c.detalle, tono: 'neutro' };
    }
  }
}

/**
 * La frase de arriba de la pantalla: cuántas esperan, cuántas ya vencieron y
 * cuántas están por vencer.
 *
 * Con la bandeja caída (`pendientes` null) NO dice "nada espera tu decisión":
 * es la afirmación más cara que puede hacer esta pantalla si es falsa.
 *
 * @param {{ pendientes: number | null, vencido: number | null, pronto: number | null }} c
 */
export function titularDelTablero({ pendientes, vencido, pronto }) {
  if (pendientes == null) {
    return { principal: 'No se pudo leer la bandeja.', alerta: null, bajada: null };
  }
  if (pendientes === 0) {
    return { principal: 'Nada espera tu decisión.', alerta: null, bajada: null };
  }
  const principal =
    pendientes === 1 ? '1 decisión te espera.' : `${pendientes} decisiones te esperan.`;
  const v = vencido ?? 0;
  const p = pronto ?? 0;
  const alerta = v > 0 ? (v === 1 ? '1 ya venció el plazo.' : `${v} ya vencieron el plazo.`) : null;
  const bajada =
    p > 0
      ? p === 1
        ? '1 más vence pronto.'
        : `${p} más vencen pronto.`
      : v === 0
        ? 'Ningún plazo vencido ni por vencer.'
        : null;
  return { principal, alerta, bajada };
}
