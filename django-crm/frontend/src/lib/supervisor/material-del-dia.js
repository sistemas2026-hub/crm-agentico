/**
 * Cómo se dice en Programación el material del día (28/10/2026). Fuera del
 * componente para poder probarlo. SPEC/objetivos/material-del-dia.md.
 */

/**
 * «Conector UPC: carga 6 unidades (ya tiene 4)», «ONU WIFI: carga 1 unidad», o
 * «Cable drop: tiene el kit completo» cuando no hay que cargar nada.
 *
 * @param {{ material: string, unidad: string, en_mano: string, necesita: string, asignado: string }} l
 */
export function lineaDeMaterial(l) {
  const tiene = Number(l.en_mano) > 0 ? ` (ya tiene ${l.en_mano})` : '';
  if (Number(l.necesita) <= 0) return `${l.material}: tiene el kit completo${tiene}`;
  return `${l.material}: carga ${cantidad(l.asignado, l.unidad)}${tiene}`;
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
