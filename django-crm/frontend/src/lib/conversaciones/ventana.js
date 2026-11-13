/**
 * La ventana de 24 h de WhatsApp, vista desde la COLA (29/10/2026).
 *
 * La vista de una conversación ya avisaba en la última hora; la cola no
 * mostraba nada, así que no se veía cuál estaba por cerrarse hasta abrirla.
 * El motor manda `ventana_whatsapp.restante_seg` en cada fila, calculado con
 * su reloj (whatsapp.estado_de_ventana). Acá solo se le descuenta lo que pasó
 * desde que se leyó la cola: el reloj del navegador puede estar corrido, y un
 * contador que arranca mal se ve igual de convincente que uno bueno.
 */

/** Desde cuántos segundos restantes la fila lo marca: dos horas. */
export const URGE_DESDE_SEG = 2 * 60 * 60;

/**
 * Segundos que le quedan a la ventana, o null si no aplica (otro canal, o el
 * cliente nunca escribió). null NO es cerrada.
 *
 * @param {any} ventana     `ventana_whatsapp` de la fila
 * @param {string|null|undefined} leidaEn  cuándo se leyó la cola (ISO)
 * @param {number} ahora    epoch ms
 * @returns {number|null}
 */
export function restanteDeVentana(ventana, leidaEn, ahora) {
  if (!ventana || ventana.abierta == null || ventana.restante_seg == null) return null;
  if (!ventana.abierta) return 0;
  const pasados = leidaEn ? Math.max(0, Math.floor((ahora - new Date(leidaEn).getTime()) / 1000)) : 0;
  return Math.max(0, ventana.restante_seg - pasados);
}

/**
 * Si la fila tiene que marcarlo: queda poco Y le toca contestar a una
 * persona. Con la IA atendiendo no hay a quién apurar: ella contesta sola.
 *
 * @param {any} c
 * @param {number|null} restante
 */
export function ventanaUrge(c, restante) {
  if (restante == null || restante <= 0 || restante > URGE_DESDE_SEG) return false;
  return [c, ...((c && c.abiertas) || [])].some(
    (x) => x && x.estado !== 'cerrada' && (x.control === 'humano' || x.control_efectivo === 'humano')
  );
}

/** «45 min», «1 h 20 min», «3 h». Un minuto como mínimo: «0 min» no se lee. */
export function comoRestante(/** @type {number} */ seg) {
  const min = Math.max(1, Math.round(seg / 60));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const resto = min % 60;
  return resto ? `${h} h ${resto} min` : `${h} h`;
}
