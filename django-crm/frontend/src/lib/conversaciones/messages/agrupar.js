/**
 * QUÉ MENSAJES DEL HILO ABREN UN GRUPO (04/11/2026).
 *
 * POR QUÉ EXISTE
 * --------------
 * Cada burbuja llevaba encima su ficha de autor y su hora. En un hilo real el
 * cliente escribe en ráfagas --«hola», «sigo sin internet», «ya reinicié»--
 * y la IA contesta en dos o tres partes: el nombre se repetía en cada una, y
 * la mitad del alto del hilo era metadato que no decía nada nuevo. WhatsApp,
 * de donde viene la costumbre de quien atiende, nombra al autor una vez por
 * ráfaga.
 *
 * Un grupo es una ráfaga del MISMO autor: misma identidad durable (la clase
 * de `autorDe` y su `quien`, para que dos personas del equipo no se fundan),
 * el mismo día, y menos de 10 minutos entre un mensaje y el siguiente. Pasado
 * ese tiempo es otra intervención y vuelve a nombrarse: quien lee necesita
 * saber que entre las dos pasó algo.
 *
 * Cualquier cosa que no sea una burbuja --separador de día, marca de cierre,
 * «ver anteriores», nota interna, evento de sistema-- corta el grupo: el
 * mensaje que viene después de una nota tiene que decir de nuevo quién habla,
 * o se leería como continuación de la nota.
 *
 * NO DECIDE NADA del contenido: no reordena, no filtra, no toca el mensaje.
 * Solo marca `inicioDeGrupo` en una copia de cada item de tipo 'msg'.
 */
import { autorDe } from '../formato.js';

/** Diez minutos: la ráfaga de alguien que escribe en varias partes. */
export const VENTANA_GRUPO_MS = 10 * 60 * 1000;

/** Si el item se dibuja como burbuja (lo que puede agruparse). */
function esBurbuja(/** @type {any} */ item) {
  if (item?.tipo !== 'msg' || !item.m) return false;
  const rol = item.m.rol;
  return rol === 'user' || rol === 'assistant';
}

/** La identidad que tiene que coincidir para seguir el grupo. */
function firma(/** @type {any} */ m) {
  const a = autorDe(m);
  // `deOtraConversacion` cambia el rótulo del cliente (sin nombre, por
  // privacidad): dos burbujas con rótulos distintos no son el mismo grupo.
  return `${a.clase}|${a.quien ?? ''}|${m?.deOtraConversacion ? 'otra' : 'esta'}`;
}

function instante(/** @type {any} */ iso) {
  const t = new Date(iso ?? '').getTime();
  return Number.isNaN(t) ? null : t;
}

function mismoDia(/** @type {number} */ a, /** @type {number} */ b) {
  return new Date(a).toDateString() === new Date(b).toDateString();
}

/**
 * @param {any[]} items  el hilo como lo arma chat.js: {tipo:'dia'|'mas'|'cierre'|'msg', ...}
 * @returns {any[]} los mismos items; los de tipo 'msg' con `inicioDeGrupo`
 */
export function agruparMensajes(items) {
  const lista = Array.isArray(items) ? items : [];
  /** @type {{ firma: string, t: number|null }|null} */
  let previo = null;
  return lista.map((item) => {
    if (!esBurbuja(item)) {
      previo = null;
      return item.tipo === 'msg' ? { ...item, inicioDeGrupo: true } : item;
    }
    const f = firma(item.m);
    const t = instante(item.m.creado_en);
    // Sin hora no se puede afirmar que fue «poco después»: abre grupo.
    const sigue =
      previo !== null &&
      previo.firma === f &&
      previo.t !== null &&
      t !== null &&
      t >= previo.t &&
      t - previo.t < VENTANA_GRUPO_MS &&
      mismoDia(previo.t, t);
    previo = { firma: f, t };
    return { ...item, inicioDeGrupo: !sigue };
  });
}
