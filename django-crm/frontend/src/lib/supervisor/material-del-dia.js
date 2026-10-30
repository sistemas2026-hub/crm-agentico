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
 * Si el Supervisor ya le cargó el material hoy: «Cargado a las 06:07». Vacío
 * si no. Sin el acta desde el 29/10/2026 (el usuario: «está de más»): el acta
 * sigue en Inventario → Reportes → Entregas, que es donde se busca.
 *
 * @param {{ cargado_en?: string | null, acta?: string }} m
 */
export function estadoDeCarga(m) {
  if (!m?.cargado_en) return '';
  return `Cargado a las ${m.cargado_en.slice(11, 16)}`;
}

/**
 * Una línea que resume los avisos del material de una cuadrilla (29/10/2026,
 * el usuario: «que se contraiga como el material»): «Falta material · sale sin
 * ONU CATV y ONU WIFI». Lo que no reconoce lo cuenta: «1 aviso más».
 *
 * @param {string[]} avisos
 */
export function resumenDeAvisos(avisos) {
  const lista = avisos ?? [];
  const sinEquipo = lista.map((a) => /^Sale sin (.+?):/.exec(a)?.[1]).filter(Boolean);
  const falta = lista.some((a) => a.startsWith('Le falta material'));
  const otros = lista.length - sinEquipo.length - (falta ? 1 : 0);
  const partes = [];
  if (falta) partes.push('Falta material');
  if (sinEquipo.length) partes.push(`${partes.length ? 'sale' : 'Sale'} sin ${unidos(sinEquipo)}`);
  if (otros > 0) partes.push(`${otros} ${otros === 1 ? 'aviso' : 'avisos'} más`);
  return partes.join(' · ');
}

/** «A», «A y B», «A, B y C». @param {string[]} cosas */
function unidos(cosas) {
  if (cosas.length <= 1) return cosas.join('');
  return `${cosas.slice(0, -1).join(', ')} y ${cosas[cosas.length - 1]}`;
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
 * Las cuentas del material del día como pastillas (29/10/2026, el usuario,
 * con la captura: «¿qué podemos hacer con esto para que se vea más
 * estético?»). Lo que está en cero no se dice, salvo las completas: «0 de 5
 * con el kit completo» también es un dato.
 *
 * @param {{ cuadrillas: number, completas: number, con_faltantes?: number, sin_carga?: number }} c
 * @returns {{ texto: string, tono: 'ok' | 'falta' | 'sin' }[]}
 */
export function pastillasDeCuentas(c) {
  /** @type {{ texto: string, tono: 'ok' | 'falta' | 'sin' }[]} */
  const salida = [{ texto: `${c.completas} de ${c.cuadrillas} con el kit completo`, tono: 'ok' }];
  if (c.con_faltantes) salida.push({ texto: `${c.con_faltantes} con faltantes`, tono: 'falta' });
  if (c.sin_carga) salida.push({ texto: `${c.sin_carga} sin carga`, tono: 'sin' });
  return salida;
}

/**
 * Lo que les falta a las bodegas, una entrada por bodega en el orden en que
 * llegan. Eran trece líneas rojas iguales, una por material
 * («BOG-SOLEDAD: faltan 2000 m de CABLE DROP (hay 0 libres…)»). `sinNada`
 * dice que no hay libre NADA de lo que se pide: casi siempre es stock que no
 * se cargó en Dexter, y se puede decir.
 *
 * @param {{ bodega: string, material: string, unidad: string, falta: string, disponible: string, pedido: string }[]} faltantes
 */
export function faltantesPorBodega(faltantes) {
  /** @type {Map<string, typeof faltantes>} */
  const por = new Map();
  for (const f of faltantes ?? []) {
    if (!por.has(f.bodega)) por.set(f.bodega, []);
    por.get(f.bodega)?.push(f);
  }
  return [...por].map(([bodega, materiales]) => ({
    bodega,
    materiales,
    sinNada: materiales.every((m) => Number(m.disponible) <= 0)
  }));
}

/** «le faltan 13 materiales», «le falta 1 material». @param {number} n */
export function cuantosFaltan(n) {
  return n === 1 ? 'le falta 1 material' : `le faltan ${n} materiales`;
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
