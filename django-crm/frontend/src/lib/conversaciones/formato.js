/**
 * Cómo se muestra un mensaje del hilo: su día, su hora, su tipo de burbuja y
 * qué dice su estado de entrega.
 *
 * POR QUÉ ESTÁ ACÁ Y NO DENTRO DEL COMPONENTE
 * -------------------------------------------
 * Mismo motivo que `estado.js`, que nació de una duplicación que se separó en
 * silencio: al partir la conversación en componentes, la página padre y el
 * hilo necesitan las mismas respuestas. Dos copias de `hora()` no se ven
 * distintas hasta el día que una cambia.
 *
 * Todo lo de acá es puro: entra un dato, sale un texto. Sin estado, sin DOM.
 */

/** Clave de día local, para agrupar el hilo. */
export function diaDe(/** @type {string} */ iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toDateString();
}

export function etiquetaDia(/** @type {string} */ iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const hoy = new Date();
  const ayer = new Date();
  ayer.setDate(hoy.getDate() - 1);
  if (d.toDateString() === hoy.toDateString()) return 'Hoy';
  if (d.toDateString() === ayer.toDateString()) return 'Ayer';
  return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'long' }).format(d);
}

export function hora(/** @type {string} */ iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' }).format(d);
}

/** El esquema admite user|assistant|tool|system; solo los dos primeros
 *  aparecen hoy (nucleo/persistencia/db.py solo registra esos), pero un
 *  rol inesperado cae en un estilo neutro en vez de romper el render. */
export const burbujaClase = (/** @type {string} */ rol) =>
  rol === 'user'
    ? 'chat-usuario'
    : rol === 'assistant'
      ? 'chat-asistente'
      : // Una nota interna NO se parece a un mensaje: si se ve como una
        // burbuja mas, alguien la va a leer como algo que se le dijo al
        // cliente. Es la mitad visual de la garantia; la otra mitad es que
        // la ruta que la guarda no toca el canal.
        rol === 'nota'
        ? 'chat-nota'
        : 'chat-otro';

/** La extensión de un adjunto, sacada del nombre o del mime. Sirve para
    decir "PDF" en vez de "application/pdf", que no le dice nada a nadie. */
export function extension(/** @type {any} */ a) {
  const delNombre = (a.descripcion || '').split('.').pop();
  if (delNombre && delNombre.length <= 5 && delNombre !== a.descripcion) {
    return delNombre.toUpperCase();
  }
  return ((a.mime || '').split('/')[1] || 'archivo').toUpperCase();
}

export const ENTREGA_TEXTO = {
  pendiente: 'Enviando…',
  enviado: 'Enviado',
  entregado: 'Entregado',
  leido: 'Leído',
  // D24: la IA la calculó, pero una persona tomó el control antes de que
  // saliera. No se envió y no se ofrece reintentar: ya atiende una persona.
  descartado: 'No enviada: una persona tomó el control'
};
