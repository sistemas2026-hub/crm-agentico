/**
 * Cómo se dice en Programación el material del día (28/10/2026). Fuera del
 * componente para poder probarlo. SPEC/objetivos/material-del-dia.md.
 */

/**
 * «Conector UPC: carga 6 unidades (ya tiene 4)», «ONU WIFI: carga 1 unidad», o
 * «Cable drop: tiene el kit completo» cuando no hay que cargar nada.
 *
 * Lo que falta va en la MISMA línea: «CABLE COAXIAL: carga 100 m (faltan 100
 * m)», «CHAZO: no hay en bodega (faltan 10 unidades)». Una línea aparte por
 * faltante llenaba la tarjeta (captura del usuario, 28/10/2026).
 *
 * @param {{ material: string, unidad: string, en_mano: string, necesita: string, asignado: string, falta?: string }} l
 */
export function lineaDeMaterial(l) {
  const tiene = Number(l.en_mano) > 0 ? `ya tiene ${l.en_mano}` : '';
  const falta = Number(l.falta) > 0 ? `faltan ${cantidad(l.falta ?? '0', l.unidad)}` : '';
  const entre = [tiene, falta].filter(Boolean).join(' · ');
  const extra = entre ? ` (${entre})` : '';
  if (Number(l.necesita) <= 0) return `${l.material}: tiene el kit completo${extra}`;
  if (Number(l.asignado) <= 0) return `${l.material}: no hay en bodega${extra}`;
  return `${l.material}: carga ${cantidad(l.asignado, l.unidad)}${extra}`;
}

/**
 * El rótulo de la lista plegada: «Ver los 14 materiales del kit · 9
 * incompletos».
 *
 * @param {{ falta?: string }[]} lineas
 */
export function resumenDeLineas(lineas) {
  const n = lineas.length;
  const incompletos = lineas.filter((l) => Number(l.falta) > 0).length;
  const base = n === 1 ? 'Ver el material del kit' : `Ver los ${n} materiales del kit`;
  return incompletos ? `${base} · ${incompletos} incompleto${incompletos === 1 ? '' : 's'}` : base;
}

/** Lo que devuelve el backend cuando lo eligió una persona en el panel. */
export const POR_UNA_PERSONA = 'lo eligió una persona';

/**
 * Por qué ese kit o esa bodega: «elegido por una persona», o «lo eligió el
 * Supervisor: su zona la nombra» (28/10/2026: «la idea era que lo hiciera el
 * Supervisor»).
 *
 * @param {string} motivo
 */
export function porQue(motivo) {
  if (!motivo) return '';
  return motivo === POR_UNA_PERSONA ? 'elegido por una persona' : `lo eligió el Supervisor: ${motivo}`;
}

/**
 * La primera opción del panel: dejar que elija el Supervisor, diciendo qué
 * elegiría hoy.
 *
 * @param {string} eligeElSupervisor el nombre, o vacío si no puede elegir
 */
export function opcionDelSupervisor(eligeElSupervisor) {
  return eligeElSupervisor
    ? `Que elija el Supervisor (hoy: ${eligeElSupervisor})`
    : 'Que elija el Supervisor (hoy no puede: ver el motivo)';
}

/**
 * Si el Supervisor ya le cargó el material hoy (fase 3, 28/10/2026): «Cargado
 * por el Supervisor a las 06:07 · acta MAT-20261028-1a2b3c4d». Vacío si no.
 *
 * @param {{ cargado_en?: string | null, acta?: string }} m
 */
export function estadoDeCarga(m) {
  if (!m?.cargado_en) return '';
  return `Cargado por el Supervisor a las ${m.cargado_en.slice(11, 16)} · acta ${m.acta}`;
}

/**
 * La línea de arriba del material del día: cuántas ya se cargaron, o que es
 * todavía una propuesta.
 *
 * @param {{ cargado_en?: string | null }[]} cuadrillas
 */
export function tituloDelMaterial(cuadrillas) {
  const cargadas = cuadrillas.filter((c) => c.cargado_en).length;
  if (!cargadas) return 'Material del día · propuesta: el Supervisor todavía no cargó nada';
  return `Material del día · el Supervisor ya cargó ${cargadas} de ${cuadrillas.length} cuadrillas`;
}

/**
 * «1 unidad», «6 unidades», «300 metros».
 * @param {string} n
 * @param {string} unidad
 */
export function cantidad(n, unidad) {
  if (Number(n) === 1 && unidad === 'unidades') return '1 unidad';
  return `${n} ${unidad}`;
}

/**
 * Del formulario de configuración al cuerpo del PUT. Los campos se llaman
 * `kit:<código de labor>` y `bodega:<id de cuadrilla>`; vacío = sin kit / sin
 * bodega. Solo viaja lo que el formulario trae.
 *
 * @param {FormData} f
 * @returns {{ kits: Record<string, string|null>, bodegas: Record<string, string|null> }}
 */
export function cuerpoDeConfiguracion(f) {
  /** @type {Record<string, string|null>} */
  const kits = {};
  /** @type {Record<string, string|null>} */
  const bodegas = {};
  for (const [clave, valor] of f.entries()) {
    const v = String(valor ?? '').trim() || null;
    if (clave.startsWith('kit:')) kits[clave.slice(4)] = v;
    else if (clave.startsWith('bodega:')) bodegas[clave.slice(7)] = v;
  }
  return { kits, bodegas };
}
