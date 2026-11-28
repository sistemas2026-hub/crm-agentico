/**
 * LAS ÓRDENES DE UNA CUADRILLA, EN FILAS  --  24/11/2026
 *
 * El usuario, con un día de 47 órdenes a la vista: «cuando hay muchas
 * órdenes, toca bajar demasiado para verlas todas». Cada orden era una tarjeta
 * de ~190 px y la sección medía ~4.900 px: cinco pantallas y media, y la
 * cuadrilla de 20 órdenes sola llegaba a 4.000.
 *
 * Ahora cada orden es UNA FILA de dos renglones (lugar, OT, asunto; estado,
 * barrio, vencimiento y lo que pide atención) que se abre a la tarjeta de
 * siempre, `OrdenDelDia.svelte`, sin tocarla: lo que se puede hacer con una
 * orden sigue estando, un clic más adentro.
 *
 * Lo que decide qué se ve vive acá, en funciones puras, porque las pruebas de
 * este proyecto renderizan en el servidor y no pueden tocar un botón.
 */

import { tonoDelVencimiento } from './dia-publicado.js';

/** Cuántas filas se ven antes de plegar el resto de una cuadrilla. */
export const TOPE_VISIBLE = 8;

/** Los filtros de arriba, en el orden en que se muestran. */
export const FILTROS = /** @type {const} */ ([
  { id: 'todas', texto: 'Todas' },
  { id: 'atencion', texto: 'Piden atención' },
  { id: 'vencidas', texto: 'Vencidas' },
  { id: 'sin_terminar', texto: 'Sin terminar' }
]);

const TERMINADAS = ['cerrada', 'cancelada'];

/**
 * Lo que una orden le pide a alguien de la oficina, en palabras cortas para
 * la fila. Vacío si no pide nada. Son las mismas cosas que la tarjeta muestra
 * con un bloque propio: si la fila no las nombrara, plegar la tarjeta las
 * escondería.
 *
 * @param {any} o
 * @returns {string[]}
 */
export function motivosDeAtencion(o) {
  if (!o) return [];
  /** @type {string[]} */
  const m = [];
  if (o.bloqueo) m.push('Detenida');
  if (o.devolucion) m.push('Devuelta');
  if (o.revision) m.push('Por revisar');
  //  27/11/2026: una instalación que valida una persona la cierra el técnico
  //  con «Finalizar trabajo» (que cierra también el ticket): no está «lista
  //  para cerrar» por la oficina.
  else if (o.estado === 'completada_campo' && o.validacion === 'aprobado' && o.la_cierra_el_tecnico) m.push('Falta que el técnico finalice');
  else if (o.estado === 'completada_campo' && o.validacion === 'aprobado') m.push('Lista para cerrar');
  if (o.seguimiento?.tipo === 'vencido') m.push('Sin reporte');
  if (o.aviso === 'no_llego') m.push('No llegó al teléfono');
  return m;
}

/** @param {any} o */
export function pideAtencion(o) {
  return motivosDeAtencion(o).length > 0;
}

/**
 * Si la fila arranca abierta: lo que pide atención, y la orden sobre la que
 * acaba de volver el resultado de una acción (mover, destrabar, cerrar), para
 * que ese resultado —que se dibuja DENTRO de la tarjeta— no quede plegado.
 *
 * @param {any} o
 * @param {any} [form]
 */
export function arrancaAbierta(o, form = null) {
  return pideAtencion(o) || (Boolean(form?.orden) && form.orden === o?.id);
}

/**
 * @param {any} o
 * @param {string} filtro uno de FILTROS
 * @param {string} texto lo escrito en el buscador
 * @param {string} dia AAAA-MM-DD
 */
export function pasaElFiltro(o, filtro, texto, dia) {
  if (filtro === 'atencion' && !pideAtencion(o)) return false;
  if (filtro === 'vencidas' && tonoDelVencimiento(o?.vence_en, dia) !== 'vencida') return false;
  if (filtro === 'sin_terminar' && TERMINADAS.includes(o?.estado)) return false;
  const q = normalizar(texto);
  if (!q) return true;
  return [`ot ${o?.numero}`, `#${o?.numero}`, String(o?.numero ?? ''), o?.asunto, o?.tipo, o?.cliente, o?.barrio, o?.direccion]
    .some((campo) => normalizar(campo).includes(q));
}

/**
 * Cuántas órdenes del día entran en cada filtro, para el número de su botón.
 *
 * @param {any[]} cuadrillas
 * @param {string} dia
 * @returns {Record<string, number>}
 */
export function cuentasDeLosFiltros(cuadrillas, dia) {
  const ordenes = (cuadrillas ?? []).flatMap((c) => c?.ordenes ?? []);
  return Object.fromEntries(
    FILTROS.map((f) => [f.id, ordenes.filter((o) => pasaElFiltro(o, f.id, '', dia)).length])
  );
}

/**
 * Qué filas se ven y cuáles quedan plegadas en una cuadrilla.
 *
 * Sin filtro, las primeras `TOPE_VISIBLE` en el orden del día y el resto
 * plegado, diciendo cuántas de las plegadas piden atención: el orden del día
 * no se rompe para subir una, pero tampoco se esconde que está. Con un filtro
 * o una búsqueda no se pliega nada: ya se pidió ver justo eso.
 *
 * @param {any[]} ordenes
 * @param {{ filtro?: string, texto?: string, dia: string }} opciones
 */
export function partirLasFilas(ordenes, { filtro = 'todas', texto = '', dia }) {
  const filtrando = filtro !== 'todas' || normalizar(texto) !== '';
  const lista = (ordenes ?? []).filter((o) => pasaElFiltro(o, filtro, texto, dia));
  //  Plegar una o dos no ahorra nada y suma un clic: con 10 se ven las 10.
  if (filtrando || lista.length <= TOPE_VISIBLE + 2) {
    return { visibles: lista, plegadas: [], atencionPlegada: 0, filtrando, total: (ordenes ?? []).length };
  }
  const plegadas = lista.slice(TOPE_VISIBLE);
  return {
    visibles: lista.slice(0, TOPE_VISIBLE),
    plegadas,
    atencionPlegada: plegadas.filter(pideAtencion).length,
    filtrando,
    total: lista.length
  };
}

/** @param {unknown} s */
function normalizar(s) {
  return String(s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}
