/**
 * ============================================================================
 *  EL POR QUÉ DE UNA FOTO, EN UN RENGLÓN  --  21/11/2026
 * ============================================================================
 * EL ERROR QUE LO ORIGINÓ. El usuario, con la OT #283 en la pantalla: «el
 * texto que describe es muy largo». Cada foto con algo que mirar abría sola
 * su detalle y volcaba, en una tarjeta de 270 px de ancho:
 *
 *   - la instrucción ENTERA de la plantilla, que está escrita para el modelo
 *     («Copiá los dígitos tal como aparecen… No redondees ni reacomodes la
 *     coma»), no para quien revisa;
 *   - la prosa entera del modelo;
 *   - y sus tres líneas de marca tal cual: «CATALOGO: no MUESTRA: si
 *     ATENCION: si».
 *
 * Doce renglones por foto. El 17/11 ya se había pedido lo mismo —«que mejor
 * muestre si pasa, y cuando no pase, por qué»— y se resolvió a medias: la
 * foto sin problemas quedó en una línea, pero la que tenía un problema
 * seguía abriendo todo.
 *
 * LO QUE HACE ESTE ARCHIVO. Dos funciones puras, sin dato nuevo:
 *
 *   `sinMarcas`  quita las marcas del protocolo. Son cómo el código habla
 *                consigo mismo (`campo/inspeccion_visual.py`); la app del
 *                técnico ya las quitaba (`analisis_para_el_tecnico.py`) y
 *                esta pantalla no.
 *   `porQue`     el motivo en un renglón: la primera frase del modelo, que
 *                arranca por la conclusión, y las que entren después.
 *
 * LO QUE NO HACE: decidir. Si la foto pasa o no lo sigue diciendo
 * `estado-de-la-foto.js` con los campos que el backend ya calculó. Acá solo
 * se acorta lo que se LEE; el texto entero sigue a un clic, en «ver detalle».
 * ============================================================================
 */

/**
 * Cuánto entra. La tarjeta mide ~270 px y a 12 px son unos 40 caracteres por
 * línea: 110 son tres líneas como mucho. Medido contra los dos textos de la
 * OT #283: el de 103 caracteres entra entero, y el de 190 se queda con su
 * primera frase (64) porque la segunda ya no entra.
 */
export const TOPE_DEL_POR_QUE = 110;

const VALOR = '(?:no se sabe|s[ií]|no)';
const CLAVE = '(?:CAT[AÁ]LOGO|MUESTRA|ATENCI[OÓ]N)';
//  En MAYÚSCULAS y en cualquier lugar del renglón: así las escribe el
//  protocolo, y el modelo a veces las deja todas en la misma línea.
const MARCA_SUELTA = new RegExp(
  `(^|[\\s.;,])${CLAVE}\\s*:\\s*${VALOR}(?=$|[\\s.;,])\\.?`, 'g');
//  Al empezar un renglón, también en minúsculas: misma regla que
//  `_resumen` en el backend.
const MARCA_AL_EMPEZAR = new RegExp(
  `^\\s*${CLAVE}\\s*:\\s*${VALOR}\\s*\\.?\\s*$`, 'i');

/**
 * El texto del modelo sin las marcas del protocolo.
 * @param {string | null | undefined} texto
 * @returns {string}
 */
export function sinMarcas(texto) {
  return String(texto ?? '')
    .split(/\r?\n/)
    .filter((renglon) => !MARCA_AL_EMPEZAR.test(renglon))
    .join(' ')
    .replace(MARCA_SUELTA, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * El motivo en un renglón.
 *
 * Se corta donde termina una FRASE, no a mitad de una: «-21.0 dBm» cortado
 * en «-21.» se leería como otro número. El punto de un decimal no separa
 * frases porque no lo sigue un espacio.
 *
 * @param {string | null | undefined} texto
 * @param {number} [tope]
 * @returns {string}
 */
export function porQue(texto, tope = TOPE_DEL_POR_QUE) {
  const limpio = sinMarcas(texto);
  if (limpio.length <= tope) return limpio;

  const frases = limpio.split(/(?<=[.!?])\s+/);
  let junto = '';
  for (const frase of frases) {
    const candidato = junto ? `${junto} ${frase}` : frase;
    if (candidato.length > tope) break;
    junto = candidato;
  }
  if (junto) return junto;

  //  La primera frase sola ya no entra: se corta en una palabra y se dice
  //  que hay más.
  const recorte = limpio.slice(0, tope - 1);
  const espacio = recorte.lastIndexOf(' ');
  const base = espacio > tope / 2 ? recorte.slice(0, espacio) : recorte;
  return `${base.replace(/[\s,;:.]+$/, '')}…`;
}
