/**
 * «Leída» y «no leída» en la Bandeja (11/11/2026), como WhatsApp Business.
 *
 * La marca es del EQUIPO y del CHAT: la guarda el motor
 * (POST /conversaciones/<id>/leida → db.marcar_leida) y la cola CALCULA los no
 * leídos de cada fila (mensajes del cliente posteriores). Acá solo se decide
 * CUÁNDO la pantalla de la conversación avisa que se leyó, y se lee el número.
 *
 * CUÁNDO SE MARCA
 * ---------------
 * - Al abrir la conversación, si la pestaña está a la vista.
 * - Cuando llega algo nuevo del cliente con la pestaña a la vista: lo trae el
 *   sondeo de la conversación (cada 5 s) o la cola dice que el chat tiene no
 *   leídos (cada 8 s). La cola cubre lo que el sondeo no ve: un mensaje que cayó
 *   en OTRA abierta del mismo chat.
 * - NUNCA en cada sondeo si no hay nada nuevo: serían doce escrituras por
 *   minuto por cada pestaña abierta, para no cambiar nada.
 * - Con la pestaña de fondo no se marca: que esté abierta en otra pestaña no
 *   es que alguien la haya leído.
 */

import { pendiente, enAtencion } from './estado.js';

/**
 * Los no leídos de una fila, como número. Lo que no es un número es 0.
 * Es la cuenta CRUDA del motor: decide cuándo avisar que se leyó. Lo que se
 * MUESTRA es `noLeidosVisibles`.
 * @param {any} c
 */
export function noLeidos(c) {
  const n = Number(c?.no_leidos);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/**
 * Hay una persona en el caso: alguien lo pidió para una persona o una persona
 * lo está atendiendo. Es EXACTAMENTE la regla de las pestañas «Por atender» y
 * «En atención» (estado.js: `pendiente`, `enAtencion`), compuesta y no
 * copiada.
 *
 * POR QUÉ ACÁ Y NO EN EL MOTOR (11/11/2026, auditoría H5). CLAUDE.md §12 pide
 * que el backend decida. Pero «persona en el caso» no existe en el motor: la
 * proyección (nucleo/relevo/proyeccion.py) decide bandas con OTROS campos
 * (control, asignación), y las pestañas se deciden acá, en estado.js. Una
 * copia en Python sería una segunda definición de la misma regla, y estado.js
 * ya documenta qué pasa con dos copias: el 07/09/2026 la cabecera decía 41 y
 * el panel 44. Acá, un chat de «Por atender» sin contador no puede pasar por
 * construcción. Mover la regla al motor es mover las pestañas, y eso es otro
 * trabajo.
 *
 * @param {any} c  una fila de la cola (un chat, con sus `abiertas`)
 */
export const hayPersonaEnElCaso = (c) => !!c && (pendiente(c) || enAtencion(c));

/**
 * Los no leídos que la Bandeja MUESTRA (contador, negrita) y que cuenta el
 * filtro «No leídas» (11/11/2026, decisión de producto H5): solo con una
 * persona en el caso. Un chat que lleva la IA tiene mensajes del cliente que
 * nadie abrió POR DISEÑO -- los contesta la IA --, y pintarlos en negrita
 * convertía la cola entera en un aviso que no pide nada. La cuenta del motor
 * no cambia: si una persona toma el chat, aparecen todos los que nadie leyó.
 * @param {any} c
 */
export function noLeidosVisibles(c) {
  return hayPersonaEnElCaso(c) ? noLeidos(c) : 0;
}

/**
 * Cuándo escribió el cliente por última vez en estos mensajes, en ms, o null.
 * Solo `rol === 'user'`: una respuesta nuestra no es algo que haya que leer.
 * @param {any[] | null | undefined} mensajes
 */
export function ultimoDelCliente(mensajes) {
  let max = null;
  for (const m of mensajes ?? []) {
    if (m?.rol !== 'user' || !m.creado_en) continue;
    const t = Date.parse(m.creado_en);
    if (Number.isFinite(t) && (max === null || t > max)) max = t;
  }
  return max;
}

/**
 * La fila de la cola del chat de esta conversación: la que la tiene como
 * representante o entre sus `ids` (la cola agrupa por número).
 * @param {any[] | null | undefined} conversaciones
 * @param {string} id
 */
export function filaDelChat(conversaciones, id) {
  return (conversaciones ?? []).find((c) => c?.id === id || (c?.ids ?? []).includes(id)) ?? null;
}

/**
 * Si la conversación abierta ofrece «Marcar como no leída» (11/11/2026, H5):
 * solo donde el contador se va a ver. En un chat que lleva la IA la marca no
 * dejaría nada en negrita, y un botón que no produce nada visible parece roto.
 *
 * Se mira la fila del chat en la cola (trae las otras abiertas del número); si
 * la cola no la tiene -- acotada, o todavía cargando --, la conversación
 * misma, que trae los campos de las dos reglas.
 *
 * @param {any[] | null | undefined} conversaciones  la cola
 * @param {any} conversacion  la abierta en pantalla
 */
export function ofreceMarcarNoLeida(conversaciones, conversacion) {
  return hayPersonaEnElCaso(filaDelChat(conversaciones, conversacion?.id) ?? conversacion);
}

/**
 * Si la pantalla tiene que avisar ahora que se leyó.
 *
 * `colaLeidaEn` y `marcadaEn` existen por una carrera medible: la cola que se
 * leyó ANTES de que llegara la marca todavía dice «3 sin leer», y sin esto la
 * pantalla volvería a marcar con cada cola vieja. Solo cuenta lo que la cola
 * dice si la cola se leyó DESPUÉS de la última marca.
 *
 * @param {{
 *   visible: boolean,           pestaña a la vista
 *   enVuelo?: boolean,          ya hay una marca viajando
 *   marcadaAlAbrir: boolean,    ya se marcó una vez desde que se abrió
 *   marcadaEn?: number | null,  cuándo se confirmó la última marca (ms)
 *   ultimoCliente?: number | null,  último mensaje del cliente que ve la pantalla (ms)
 *   marcadoHasta?: number | null,   el último del cliente que había al marcar (ms)
 *   noLeidosEnCola?: number,    lo que dice la fila de la cola
 *   colaLeidaEn?: number | null cuándo se leyó esa cola (ms)
 * }} estado
 */
export function debeMarcarLeida(estado) {
  const { visible, enVuelo, marcadaAlAbrir, marcadaEn, ultimoCliente, marcadoHasta,
    noLeidosEnCola, colaLeidaEn } = estado;
  if (!visible || enVuelo) return false;
  if (!marcadaAlAbrir) return true;
  if (ultimoCliente != null && (marcadoHasta == null || ultimoCliente > marcadoHasta)) return true;
  if ((noLeidosEnCola ?? 0) > 0 && colaLeidaEn != null && marcadaEn != null && colaLeidaEn > marcadaEn) {
    return true;
  }
  return false;
}
