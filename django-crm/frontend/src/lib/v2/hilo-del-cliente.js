/**
 * Cómo se lee una orden de campo en el ticket, en su página y en la ficha del
 * cliente (12/11/2026). Funciones puras, sin red: el dato lo arma el backend
 * (`campo/hilo_del_cliente.py`); esto solo decide el tono y el texto.
 */

/** @type {Record<string, 'ink'|'slate'|'clay'|'rust'|'moss'>} */
const TONO_ESTADO = {
  asignada: 'ink',
  en_camino: 'clay',
  en_sitio: 'clay',
  bloqueada: 'rust',
  completada_campo: 'moss',
  correccion_requerida: 'rust',
  cerrada: 'moss',
  cancelada: 'slate'
};

/** @param {string | null | undefined} estado */
export function tonoDeEstado(estado) {
  return TONO_ESTADO[String(estado ?? '')] ?? 'slate';
}

/** El rótulo con que se nombra una orden en todas partes. */
/** @param {number | string | null | undefined} numero */
export function rotuloDeOrden(numero) {
  return numero == null || numero === '' ? 'OT' : `OT-${numero}`;
}

/**
 * Un día `AAAA-MM-DD` legible, sin pasar por `Date` (que lo correría al día
 * anterior en Bogotá: medianoche UTC son las 7 de la tarde del día previo).
 *
 * @param {string | null | undefined} dia
 */
export function diaLegible(dia) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dia ?? ''));
  if (!m) return null;
  const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  return `${Number(m[3])} ${MESES[Number(m[2]) - 1]} ${m[1]}`;
}

/**
 * Un instante en la hora de Bogotá, en el servidor y en el navegador por igual.
 *
 * @param {string | null | undefined} iso
 */
export function instanteLegible(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString('es-CO', {
    timeZone: 'America/Bogota',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  });
}

/**
 * Quién va: el técnico y, si se sabe, la cuadrilla del día.
 *
 * @param {{ tecnico?: string | null, cuadrilla?: string | null, integrantes?: number }} o
 */
export function quienVa(o) {
  if (!o?.tecnico) return 'Sin técnico asignado';
  const mas = (o.integrantes ?? 1) > 1 ? ` y ${o.integrantes - 1} más` : '';
  return o.cuadrilla ? `${o.tecnico}${mas} · ${o.cuadrilla}` : `${o.tecnico}${mas}`;
}
