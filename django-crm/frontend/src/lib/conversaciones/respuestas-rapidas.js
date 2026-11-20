/**
 * RESPUESTAS RÁPIDAS  --  11/11/2026
 *
 * Escribir «/» en el compositor abre la lista de textos guardados de la
 * empresa, como WhatsApp Business: «/sal» filtra a «/saludo», Enter lo
 * reemplaza por su texto. La lista se edita en Ajustes → Bandeja y viaja con
 * la conversación (Conversaciones.respuestas_rapidas en el motor).
 *
 * Esto es la LÓGICA, sin DOM: qué palabra se está escribiendo, qué respuestas
 * coinciden y cómo queda el texto al elegir. Vive aparte del componente para
 * poder probarla sin dibujarlo -- y porque «Enter elige en vez de enviar»
 * depende de que `consultaDeBarra` diga la verdad.
 *
 * `{nombre}` se resuelve ACÁ y no en el motor: es el primer nombre del
 * cliente de ESTA conversación, y la pantalla es la que la tiene abierta.
 * Sin nombre conocido se quita sin dejar la frase rota: «Hola {nombre}, ¿en
 * qué te ayudo?» queda «Hola, ¿en qué te ayudo?», no «Hola , ¿en qué…».
 */

/** Cuántas se muestran a la vez. Más es una lista que hay que leer, y la
 *  idea es escribir dos letras más. */
export const MAXIMO_VISIBLES = 8;

/**
 * La «/palabra» que se está escribiendo, o `null`.
 *
 * Cuenta solo si la barra abre una palabra: al principio del texto o después
 * de un espacio o salto de línea, y si el cursor está DENTRO de esa palabra.
 * «24/7» o «y/o» no abren nada -- la barra está pegada a otra letra.
 *
 * @param {string} texto
 * @param {number} cursor posición del cursor (selectionStart)
 * @returns {{ desde: number, hasta: number, filtro: string } | null}
 *   `desde` es la posición de la barra; `hasta`, el fin de la palabra (puede
 *   pasar el cursor si se está editando en el medio); `filtro`, lo escrito
 *   entre la barra y el cursor.
 */
export function consultaDeBarra(texto, cursor) {
  const t = String(texto ?? '');
  const c = Math.max(0, Math.min(Number.isFinite(cursor) ? cursor : t.length, t.length));
  let inicio = c;
  while (inicio > 0 && !/\s/.test(t[inicio - 1])) inicio--;
  if (t[inicio] !== '/') return null;
  const filtro = t.slice(inicio + 1, c);
  // Otra barra adentro («/a/b») ya no es un atajo: es una ruta o una fecha.
  if (filtro.includes('/')) return null;
  let fin = c;
  while (fin < t.length && !/\s/.test(t[fin])) fin++;
  return { desde: inicio, hasta: fin, filtro };
}

/** Minúsculas y sin tildes: «/atencion» encuentra «atención» en el texto. */
const plano = (/** @type {string} */ s) =>
  String(s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();

/**
 * Las respuestas que coinciden con `filtro`, en orden de utilidad: primero
 * las que EMPIEZAN con lo escrito (lo que la mano espera de un atajo), después
 * las que lo contienen en el atajo, y al final las que lo contienen en el
 * texto -- para quien recuerda qué dice y no cómo se llama. Sin filtro, todas
 * en el orden en que se guardaron.
 *
 * @param {{ atajo: string, texto: string }[]} respuestas
 * @param {string} filtro
 */
export function filtrarRespuestas(respuestas, filtro) {
  const lista = Array.isArray(respuestas) ? respuestas.filter((r) => r?.atajo && r?.texto) : [];
  const f = plano(filtro).trim();
  if (!f) return lista.slice(0, MAXIMO_VISIBLES);
  const empieza = [];
  const contiene = [];
  const enTexto = [];
  for (const r of lista) {
    const a = plano(r.atajo);
    if (a.startsWith(f)) empieza.push(r);
    else if (a.includes(f)) contiene.push(r);
    else if (plano(r.texto).includes(f)) enTexto.push(r);
  }
  return [...empieza, ...contiene, ...enTexto].slice(0, MAXIMO_VISIBLES);
}

/**
 * El primer nombre, para saludar. Los nombres llegan del sistema del ISP y
 * muchas veces EN MAYÚSCULAS («ANA MARÍA PÉREZ»): saludar «Hola ANA» le grita
 * al cliente, así que uno escrito todo en mayúsculas se pasa a «Ana». Uno
 * que ya trae minúsculas se respeta como está («McKenzie»).
 *
 * @param {string | null | undefined} nombreCompleto
 */
export function primerNombre(nombreCompleto) {
  const primero = String(nombreCompleto ?? '').trim().split(/\s+/)[0] ?? '';
  if (!primero || !/\p{L}/u.test(primero)) return '';
  if (primero === primero.toUpperCase()) {
    return primero.charAt(0) + primero.slice(1).toLowerCase();
  }
  return primero;
}

/**
 * El texto de una respuesta con `{nombre}` resuelto.
 *
 * Sin nombre, el hueco se quita y se arregla lo que queda alrededor: el
 * espacio antes de una coma o un signo, el espacio doble, y la mayúscula si
 * la frase empezaba con el nombre.
 *
 * @param {string} texto
 * @param {string} nombre el primer nombre, o '' si no se conoce
 */
export function resolverNombre(texto, nombre) {
  const t = String(texto ?? '');
  if (!/\{nombre\}/i.test(t)) return t;
  if (nombre) return t.replace(/\{nombre\}/gi, nombre);
  const empezabaConNombre = /^\s*[¡¿]?\s*\{nombre\}/i.test(t);
  let r = t
    .replace(/[ \t]*\{nombre\}/gi, '')
    // «Hola , ¿…»  ->  «Hola, ¿…»;  «Hola !»  ->  «Hola!»
    .replace(/[ \t]+([,.;:!?])/g, '$1')
    // «¡ !» o «¿ ?» que quedaron vacíos
    .replace(/¡\s*!/g, '')
    .replace(/¿\s*\?/g, '')
    .replace(/[ \t]{2,}/g, ' ')
    // Lo que el nombre dejó al principio: «, gracias» -> «gracias»
    .replace(/^[ \t]*[,;:][ \t]*/, '')
    .replace(/^[ \t]+/, '');
  if (empezabaConNombre) r = r.replace(/^([¡¿]?)(\p{Ll})/u, (_, signo, letra) => signo + letra.toUpperCase());
  return r;
}

/**
 * Qué hace una tecla mientras se escribe en el compositor, en lo que toca a
 * la lista de respuestas rápidas. `null` = la tecla no es de la lista y sigue
 * su camino de siempre (Enter envía, Shift+Enter salta de línea).
 *
 * LA REGLA QUE IMPORTA: con la lista abierta, Enter y Tab ELIGEN. Nunca
 * devuelve `null` para Enter con la lista abierta -- si lo hiciera, Enter
 * mandaría «/sal» al cliente en vez de insertar «/saludo».
 *
 * @param {{ key: string, shiftKey?: boolean }} tecla
 * @param {boolean} listaAbierta
 * @param {number} activa el índice de la opción marcada
 * @param {number} cuantas cuántas opciones hay
 * @returns {{ accion: 'mover', activa: number } | { accion: 'elegir' } | { accion: 'cerrar' } | null}
 */
export function teclaDeLaLista(tecla, listaAbierta, activa, cuantas) {
  if (!listaAbierta || cuantas <= 0) return null;
  if (tecla.key === 'ArrowDown' || tecla.key === 'ArrowUp') {
    const paso = tecla.key === 'ArrowDown' ? 1 : -1;
    return { accion: 'mover', activa: (activa + paso + cuantas) % cuantas };
  }
  if ((tecla.key === 'Enter' && !tecla.shiftKey) || tecla.key === 'Tab') return { accion: 'elegir' };
  if (tecla.key === 'Escape') return { accion: 'cerrar' };
  return null;
}

/**
 * El texto del compositor después de elegir una respuesta: la «/palabra» se
 * reemplaza por el texto resuelto, y el cursor queda al final de lo
 * insertado -- listo para seguir escribiendo o para Enter.
 *
 * @param {string} texto lo que había en el cuadro
 * @param {{ desde: number, hasta: number }} consulta lo que devolvió consultaDeBarra
 * @param {{ texto: string }} respuesta
 * @param {string} nombre el primer nombre del cliente, o ''
 * @returns {{ texto: string, cursor: number }}
 */
export function insertarRespuesta(texto, consulta, respuesta, nombre) {
  const t = String(texto ?? '');
  const resuelto = resolverNombre(respuesta?.texto ?? '', nombre);
  const antes = t.slice(0, consulta.desde);
  const despues = t.slice(consulta.hasta);
  // Si lo que sigue arranca pegado (una palabra), un espacio para no fundirlas.
  const separador = despues && !/^\s/.test(despues) ? ' ' : '';
  return { texto: antes + resuelto + separador + despues, cursor: antes.length + resuelto.length };
}
