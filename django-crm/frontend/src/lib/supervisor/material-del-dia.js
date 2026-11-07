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
  const sinEquipo = lista.map(equipoDelAviso).filter(Boolean);
  const falta = lista.some((a) => a.startsWith('Le falta material'));
  const otros = lista.length - sinEquipo.length - (falta ? 1 : 0);
  const partes = [];
  if (falta) partes.push('Falta material');
  if (sinEquipo.length) partes.push(`${partes.length ? 'sale' : 'Sale'} sin ${unidos(sinEquipo)}`);
  if (otros > 0) partes.push(`${otros} ${otros === 1 ? 'aviso' : 'avisos'} más`);
  return partes.join(' · ');
}

/** El equipo que nombra un aviso «Sale sin X: …», o `null`. @param {string} a */
function equipoDelAviso(a) {
  return /^Sale sin (.+?):/.exec(a)?.[1] ?? null;
}

/**
 * LA PASTILLA DE LA TARJETA (07/11/2026). El usuario, con la captura: «qué
 * otro arreglo se puede hacer para que no se vea tan maluco».
 *
 * `resumenDeAvisos` escribía «Falta material · sale sin ONU CATV y ONU WIFI»
 * en rojo y en negrita, igual en las cuatro tarjetas. «Falta material» ya lo
 * dicen las pastillas de arriba —«5 con faltantes», «BOG-SOLEDAD le faltan 14
 * materiales»—, así que repetirlo en cada tarjeta gasta la única línea que
 * tenía algo propio que decir: QUÉ no puede hacer ESTA cuadrilla.
 *
 * Cuando el aviso nombra equipo, la pastilla dice solo eso. El texto completo
 * no se pierde: sigue adentro del desplegable.
 *
 * @param {string[]} avisos
 */
export function pastillaDeAvisos(avisos) {
  const lista = avisos ?? [];
  const sinEquipo = lista.map(equipoDelAviso).filter(Boolean);
  if (sinEquipo.length) return `Sin ${unidos(/** @type {string[]} */ (sinEquipo))}`;
  return resumenDeAvisos(lista);
}

/**
 * EL EQUIPO QUE FALTA HOY, contado por cuadrillas y UNA sola vez arriba. Es lo
 * que las tarjetas repetían y las pastillas de cuentas no decían: cuántas
 * materiales faltan ya se sabía, pero no QUÉ equipo ni a cuántas les pega.
 *
 * Se cuenta por cuadrilla, no por aviso: lo que el Supervisor decide con esto
 * es a qué bodega llamar y cuánto equipo mover.
 *
 * @param {{ avisos?: string[] }[]} [cuadrillas] el material de cada cuadrilla
 * @returns {{ equipo: string, cuadrillas: number }[]} de la más a la menos
 */
export function equipoQueFalta(cuadrillas) {
  /** @type {Map<string, number>} */
  const cuenta = new Map();
  for (const m of cuadrillas ?? []) {
    //  Dos avisos del mismo equipo en una cuadrilla siguen siendo UNA
    //  cuadrilla: si no, «4 cuadrillas» podría salir con tres.
    const vistos = new Set();
    for (const a of m?.avisos ?? []) {
      const equipo = equipoDelAviso(a);
      if (!equipo || vistos.has(equipo)) continue;
      vistos.add(equipo);
      cuenta.set(equipo, (cuenta.get(equipo) ?? 0) + 1);
    }
  }
  return [...cuenta]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([equipo, cuantas]) => ({ equipo, cuadrillas: cuantas }));
}

/**
 * «Sin ONU CATV: 4 cuadrillas». @param {{ equipo: string, cuadrillas: number }} e
 */
export function pastillaDeEquipo(e) {
  return `Sin ${e.equipo}: ${e.cuadrillas} ${e.cuadrillas === 1 ? 'cuadrilla' : 'cuadrillas'}`;
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

/**
 * «faltan 13 materiales», «falta 1 material». Sin el «le» desde el
 * 07/11/2026: ahora va detrás del nombre de la bodega y dos puntos
 * («BOG-SOLEDAD: faltan 13 materiales»), donde el «le» sobra.
 *
 * @param {number} n
 */
export function cuantosFaltan(n) {
  return n === 1 ? 'falta 1 material' : `faltan ${n} materiales`;
}

/**
 * CADA BODEGA EN UNA PASTILLA (07/11/2026). El usuario, con la captura: «qué
 * otro arreglo se puede hacer para que no se vea tan maluco».
 *
 * Eran dos barras de ancho completo, una debajo de la otra, con el borde rojo
 * a la izquierda: dos bodegas ocupaban el mismo alto que las cinco pastillas
 * de cuentas de arriba, sin decir más. Como pastilla entran las dos en una
 * fila, al lado de las cuentas que ya están en esa forma; al abrirla, la tabla
 * se lleva el ancho entero.
 *
 * @param {{ bodega: string, materiales: unknown[] }} g un grupo de `faltantesPorBodega`
 */
export function pastillaDeBodega(g) {
  return `${g.bodega}: ${cuantosFaltan(g.materiales?.length ?? 0)}`;
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
 * `kit:<código de labor>`, `bodega:<id de cuadrilla>` y `apoyo:<código de
 * labor>` (30/10/2026: «si» o «no», si se toma de apoyo); vacío = sin kit /
 * sin bodega. Solo viaja lo que el formulario trae.
 *
 * @param {FormData} f
 * @returns {{ kits: Record<string, string|null>, bodegas: Record<string, string|null>, apoyos: Record<string, boolean> }}
 */
export function cuerpoDeConfiguracion(f) {
  /** @type {Record<string, string|null>} */
  const kits = {};
  /** @type {Record<string, string|null>} */
  const bodegas = {};
  /** @type {Record<string, boolean>} */
  const apoyos = {};
  for (const [clave, valor] of f.entries()) {
    const v = String(valor ?? '').trim() || null;
    if (clave.startsWith('kit:')) kits[clave.slice(4)] = v;
    else if (clave.startsWith('bodega:')) bodegas[clave.slice(7)] = v;
    else if (clave.startsWith('apoyo:') && (v === 'si' || v === 'no')) apoyos[clave.slice(6)] = v === 'si';
  }
  return { kits, bodegas, apoyos };
}
