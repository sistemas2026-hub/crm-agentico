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
/**
 * QUIÉN escribió un mensaje, a partir de lo durable (D30).
 *
 * POR QUÉ NO ALCANZA `rol`
 * ------------------------
 * `rol` es el protocolo del canal; `origen` es quien produjo el mensaje. El
 * contrato del motor admite TRES orígenes bajo el mismo rol:
 *
 *   assistant  →  { ia, sistema, humano }
 *
 * Así que clasificar por `rol` hacía que una respuesta escrita por una persona
 * se viera idéntica a una de la IA. Esta pantalla estuvo afirmando «esto lo
 * dijo Dexter» sobre mensajes que no sabía quién había escrito.
 *
 * EL NULL NO SE ADIVINA
 * ---------------------
 * `origen` viene NULL en las filas anteriores al registro de origen. NO se
 * rellena: ni por rol, ni por el contenido, ni por quién controla hoy la
 * conversación. Se dice que no se sabe. Afirmar una autoría falsa es peor que
 * admitir el hueco, y encima es irreversible de cara a quien lee el hilo.
 *
 * Tampoco se usa el control actual de la conversación: que la lleve la IA hoy
 * no dice nada sobre quién escribió un mensaje de hace tres semanas. Son dos
 * conceptos distintos.
 *
 * @param {any} m  el mensaje, tal como lo manda el motor
 * @returns {{ clase: string, etiqueta: string, quien: string|null }}
 */
const SIN_REGISTRO = Object.freeze({
  clase: 'a-sin-registro',
  etiqueta: 'Origen no registrado',
  quien: null
});

export function autorDe(m) {
  const origen = m?.origen ?? null;
  const rol = m?.rol;
  const nombre = (m?.autor_nombre || '').trim() || null;

  // La nota interna primero: es el único caso donde el rol ya es suficiente,
  // y el que más caro sale confundir -- una nota que parezca un mensaje
  // enviado se lee como algo que se le dijo al cliente.
  if (rol === 'nota') {
    return { clase: 'a-nota', etiqueta: 'Nota interna', quien: nombre };
  }
  // Sin origen no hay nada que afirmar, y da igual qué diga el rol. Esta
  // guarda va ANTES que todo lo demás a propósito: la primera versión decía
  // `origen === 'cliente' || rol === 'user'`, y ese `||` reintroducía por la
  // puerta lateral justo lo que D30 vino a eliminar -- un `user` histórico sin
  // origen registrado salía afirmado como Cliente.
  if (origen === null || origen === undefined) {
    return SIN_REGISTRO;
  }

  // De acá en adelante, cada identidad exige la COMBINACIÓN durable completa.
  // Un origen suelto no alcanza: 'cliente' bajo rol 'assistant', o 'ia' bajo
  // rol 'user', son estados que el motor no produce, y tratarlos como válidos
  // sería inventar una lectura de datos inconsistentes.
  if (rol === 'user' && origen === 'cliente') {
    return { clase: 'a-cliente', etiqueta: 'Cliente', quien: null };
  }
  if (rol === 'assistant' && origen === 'ia') {
    return { clase: 'a-ia', etiqueta: 'Dexter IA', quien: null };
  }
  if (rol === 'assistant' && origen === 'humano') {
    // Sin nombre guardado se dice que fue una persona, sin ponerle una. El
    // dueño actual de la conversación NO sirve: puede no ser quien escribió.
    return { clase: 'a-humano', etiqueta: nombre || 'Atención humana', quien: nombre };
  }
  if (rol === 'assistant' && origen === 'sistema') {
    return { clase: 'a-sistema', etiqueta: 'Sistema', quien: null };
  }
  // Cualquier otra cosa -- un rol nuevo, un origen que el motor agregue, o una
  // combinación incoherente -- cae acá. Neutro y honesto, nunca una de las
  // cinco identidades de arriba.
  return SIN_REGISTRO;
}

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
