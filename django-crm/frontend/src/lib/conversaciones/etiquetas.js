/**
 * Las etiquetas que el EQUIPO le pone a un chat (11/11/2026), como en WhatsApp
 * Business: «Cliente VIP», «Moroso», varias por chat y con color.
 *
 * NO son `c.etiqueta` (la que elige el modelo al escalar, de la taxonomía de
 * la empresa). Estas las pone una persona y no deciden nada en el motor.
 *
 * QUÉ VIENE DEL MOTOR
 * -------------------
 * - El CATÁLOGO, una vez con la cola: `[{ clave, nombre, color }]`
 *   (Conversaciones.etiquetas_del_equipo en nucleo/config/schema.py).
 * - Por fila, solo las CLAVES del chat (`c.etiquetas_del_equipo`), ya filtradas
 *   contra el catálogo: una etiqueta borrada no llega.
 *
 * Acá se cruza una cosa con la otra y se cuenta para los filtros. Nada más.
 */

/**
 * La paleta CERRADA, con los mismos ocho nombres que valida el esquema
 * (`COLORES_DE_ETIQUETA` en nucleo/config/schema.py): agregar un color es
 * tocar los dos lugares juntos.
 *
 * Hex y no tokens de `bandeja.css` a propósito: el chip también se dibuja en
 * /settings/bandeja, que está FUERA de `.bandeja` y no ve esos tokens. Texto
 * en el tono 700-800 (contraste AA sobre su fondo), fondo 50 y filete 200: el
 * mismo trío que los avisos de la Bandeja. Un color desconocido cae en gris en
 * vez de dibujarse sin color.
 */
export const COLORES = {
  gris: { texto: '#475569', fondo: '#f1f5f9', borde: '#e2e8f0' },
  rojo: { texto: '#b91c1c', fondo: '#fef2f2', borde: '#fecaca' },
  naranja: { texto: '#c2410c', fondo: '#fff7ed', borde: '#fed7aa' },
  amarillo: { texto: '#92400e', fondo: '#fffbeb', borde: '#fde68a' },
  verde: { texto: '#047857', fondo: '#ecfdf5', borde: '#a7f3d0' },
  azul: { texto: '#1d4ed8', fondo: '#eff6ff', borde: '#bfdbfe' },
  violeta: { texto: '#6d28d9', fondo: '#f5f3ff', borde: '#ddd6fe' },
  rosa: { texto: '#be185d', fondo: '#fdf2f8', borde: '#fbcfe8' }
};

/** Los nombres en el orden en que se ofrecen. */
export const NOMBRES_DE_COLOR = /** @type {(keyof typeof COLORES)[]} */ (Object.keys(COLORES));

/** Cómo se lee cada color en el selector (los nombres son claves). */
export const COLOR_LEGIBLE = {
  gris: 'Gris',
  rojo: 'Rojo',
  naranja: 'Naranja',
  amarillo: 'Amarillo',
  verde: 'Verde',
  azul: 'Azul',
  violeta: 'Violeta',
  rosa: 'Rosa'
};

/**
 * Las variables CSS del chip de un color. El valor sale SIEMPRE de la paleta
 * de arriba, nunca del dato: el `style` no puede llevar nada que no esté acá.
 * @param {string} color
 */
export function estiloDeColor(color) {
  const c = COLORES[/** @type {keyof typeof COLORES} */ (color)] ?? COLORES.gris;
  return `--etq-texto:${c.texto};--etq-fondo:${c.fondo};--etq-borde:${c.borde}`;
}

/**
 * Las etiquetas de una fila, con nombre y color, en el ORDEN DEL CATÁLOGO.
 * Una clave que no está en el catálogo no se dibuja (el motor ya las filtra;
 * esto es la segunda red, por si el catálogo de la pantalla es más nuevo que
 * la fila).
 *
 * @param {string[] | null | undefined} claves
 * @param {{ clave: string, nombre: string, color: string }[] | null | undefined} catalogo
 */
export function etiquetasDeFila(claves, catalogo) {
  const tiene = new Set(claves ?? []);
  return (catalogo ?? []).filter((e) => tiene.has(e.clave));
}

/**
 * Las que entran en la fila y cuántas quedan afuera. Dos y un «+N»: más de
 * dos chips empujan las otras marcas del renglón fuera de la columna.
 *
 * @template T
 * @param {T[]} lista
 * @param {number} [maximo]
 * @returns {{ visibles: T[], resto: number }}
 */
export function recortar(lista, maximo = 2) {
  if (lista.length <= maximo) return { visibles: lista, resto: 0 };
  return { visibles: lista.slice(0, maximo), resto: lista.length - maximo };
}

/**
 * Si un chat tiene esa etiqueta. Mira solo la fila: las etiquetas son del
 * CHAT, así que todas sus conversaciones traen las mismas.
 * @param {any} c
 * @param {string} clave
 */
export function tieneEtiqueta(c, clave) {
  return (c?.etiquetas_del_equipo ?? []).includes(clave);
}

/**
 * Los chips del filtro: cada etiqueta del catálogo con cuántas filas la
 * tienen. Solo las que tienen alguna -- un filtro que no devuelve nada es una
 * invitación a creer que la bandeja está vacía --, salvo la ELEGIDA, que se
 * queda aunque cuente 0 para que haya dónde tocar para sacarla. Mismo
 * criterio que los motivos del layout.
 *
 * @param {any[]} filas
 * @param {{ clave: string, nombre: string, color: string }[]} catalogo
 * @param {string} [elegida]
 * @returns {[{ clave: string, nombre: string, color: string }, number][]}
 */
export function contarEtiquetas(filas, catalogo, elegida = '') {
  /** @type {[{ clave: string, nombre: string, color: string }, number][]} */
  const salida = [];
  for (const e of catalogo ?? []) {
    const n = filas.filter((c) => tieneEtiqueta(c, e.clave)).length;
    if (n > 0 || e.clave === elegida) salida.push([e, n]);
  }
  return salida;
}
