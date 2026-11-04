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

/**
 * El tono de la insignia «Estado del servicio».
 *
 * Antes era rojo todo lo que no dijera «activo», y eso pintaba como cortado un
 * servicio GRATIS -- que funciona: es una cortesía, no una deuda. Y al revés,
 * «Inactivo» contiene «activo» y salía verde.
 *
 * El estado viene del ISP y no hay una lista cerrada, así que se marca en rojo
 * solo lo que dice que el servicio está limitado, en verde lo que dice que
 * anda, y lo que no se reconoce queda neutro: sin afirmar ninguna de las dos.
 * La palabra va siempre al lado, el color nunca decide solo.
 *
 * @param {unknown} estado
 * @returns {'mal'|'ok'|'neutro'}
 */
export function tonoDeEstadoServicio(estado) {
  const e = String(estado ?? '').trim().toLowerCase();
  if (!e) return 'neutro';
  if (/suspend|cortad|cancel|retirad|baja|moros|inactiv|bloque/.test(e)) return 'mal';
  if (/^(activo|activa|active|gratis|gratuito|free)$/.test(e)) return 'ok';
  return 'neutro';
}

/*
 * 04/11/2026: cómo se LEEN los datos que llegan crudos del ISP o del canal.
 *
 * Ninguna de estas funciones inventa: si el valor no tiene la forma que
 * reconocen, devuelven el texto tal como vino. Un dato mal formateado se ve
 * raro; un dato «corregido» a ciegas se ve bien y está mal.
 *
 * Y ninguna supone la empresa: no hay símbolo de moneda (el saldo de un ISP
 * puede estar en pesos, soles o dólares) ni prefijo de país inventado (el
 * teléfono ya lo trae, porque el canal entrega el número internacional).
 */

/**
 * El número del canal, legible: `573023608750` → `+57 302 360 8750`.
 *
 * Solo se agrupa lo que se reconoce con certeza --el plan colombiano, 57 más
 * diez cifras--; cualquier otro número internacional va entero con su `+`, y
 * lo que no es un número (un id opaco, un nombre) vuelve sin tocar.
 *
 * @param {unknown} valor
 * @returns {string}
 */
export function telefonoLegible(valor) {
  const texto = String(valor ?? '').trim();
  const cifras = texto.replace(/^\+/, '');
  if (!/^\d{8,15}$/.test(cifras)) return texto;
  if (/^57\d{10}$/.test(cifras)) {
    return `+57 ${cifras.slice(2, 5)} ${cifras.slice(5, 8)} ${cifras.slice(8)}`;
  }
  // Diez cifras sin indicativo son un número nacional: agruparlo se lee
  // mejor, y ponerle un `+` inventaría un número internacional que no existe
  // (`+3001234567`).
  if (/^\d{10}$/.test(cifras) && !texto.startsWith('+')) {
    return `${cifras.slice(0, 3)} ${cifras.slice(3, 6)} ${cifras.slice(6)}`;
  }
  // Con once o más cifras es el número internacional que entrega el canal.
  if (cifras.length >= 11) return `+${cifras}`;
  return texto;
}

/**
 * Lee una fecha del ISP en las formas que llegan (`30/05/2025 10:58:00`,
 * `6/11/2026`, `2026-11-06`, ISO). Devuelve las partes, o null si no la
 * reconoce. Día/mes, nunca mes/día: así las escribe el ISP.
 *
 * @param {unknown} valor
 * @returns {{ dia: number, mes: number, anio: number, hora: string|null }|null}
 */
function partesDeFecha(valor) {
  const t = String(valor ?? '').trim();
  let m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::\d{2})?)?$/);
  if (m) {
    return {
      dia: +m[1],
      mes: +m[2],
      anio: +m[3],
      hora: m[4] ? `${m[4].padStart(2, '0')}:${m[5]}` : null
    };
  }
  m = t.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (m) {
    return { dia: +m[3], mes: +m[2], anio: +m[1], hora: m[4] ? `${m[4]}:${m[5]}` : null };
  }
  return null;
}

/**
 * Una fecha en un solo formato: `dd/mm/aaaa`, y la hora sin segundos si la
 * trae. `30/05/2025 10:58:00` → `30/05/2025 10:58`; `6/11/2026` →
 * `06/11/2026`.
 *
 * @param {unknown} valor
 * @returns {string}
 */
export function fechaLegible(valor) {
  const p = partesDeFecha(valor);
  if (!p) return String(valor ?? '').trim();
  const f = `${String(p.dia).padStart(2, '0')}/${String(p.mes).padStart(2, '0')}/${p.anio}`;
  return p.hora ? `${f} ${p.hora}` : f;
}

/**
 * Cuántos días de calendario faltan para una fecha del ISP (negativo si ya
 * pasó). null si la fecha no se reconoce: sin fecha no hay «faltan N días».
 *
 * @param {unknown} valor
 * @param {Date} [hoy]
 * @returns {number|null}
 */
export function diasHasta(valor, hoy = new Date()) {
  const p = partesDeFecha(valor);
  if (!p) return null;
  const objetivo = Date.UTC(p.anio, p.mes - 1, p.dia);
  const base = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((objetivo - base) / 86_400_000);
}

/**
 * El saldo, legible y sin moneda inventada: `0.00` → `0`; `45000.00` →
 * `45.000`; `1234.5` → `1.234,50`. Los decimales se muestran solo si no son
 * cero. Lo que no es un número vuelve tal cual.
 *
 * @param {unknown} valor
 * @returns {string}
 */
export function montoLegible(valor) {
  const texto = String(valor ?? '').trim();
  if (!/^-?\d+(\.\d+)?$/.test(texto)) return texto;
  const n = Number(texto);
  const conDecimales = !Number.isInteger(n);
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: conDecimales ? 2 : 0,
    maximumFractionDigits: conDecimales ? 2 : 0
  }).format(n);
}
