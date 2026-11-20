/**
 * Las pestañas de la cola: qué chats entran en cada una, y la frase que las
 * resume arriba de la columna.
 *
 * POR QUÉ EXISTE ESTE ARCHIVO  (04/11/2026)
 * ----------------------------------------
 * Los cuatro cuadros decían «Por atender 20 · En atención 2 · Resueltas 17 ·
 * Todos 50», y 20 + 2 + 17 = 39. Los 11 que faltaban eran los chats abiertos
 * que lleva la IA sin que nadie los haya pedido ni tomado: existían, pero solo
 * se veían mezclados en «Todos». Un tablero cuyos números no suman obliga a
 * quien lo mira a desconfiar de todos.
 *
 * El predicado de cada pestaña vivía repetido dos veces en el layout (la lista
 * y el conteo de motivos), con la misma cadena de ternarios. Agregar una
 * quinta pestaña en dos lugares a mano es la forma en que una de las dos se
 * queda atrás; acá hay una sola tabla, y el harness la puede probar sin
 * compilar un `.svelte`.
 *
 * NO DEFINE ESTADOS NUEVOS: compone los tres de `estado.js`. «Lleva la IA» es
 * su complemento exacto, y por eso se escribe como «ninguno de los tres» y no
 * con una regla propia sobre `control` o `banda`, que podría desincronizarse.
 */
import { pendiente, enAtencion, resuelta } from '$lib/conversaciones/estado.js';

/**
 * Abierto, y nadie lo está pidiendo ni lo tomó: lo está contestando la IA.
 *
 * No mira `control`: la columna cruda no es el control efectivo en las
 * legadas, y el reparto «quién tiene el control ahora» ya lo cuenta el pie de
 * la Bandeja. Esta pestaña responde otra pregunta —qué queda fuera de las
 * otras tres— y la respuesta tiene que cerrar la suma.
 *
 * @param {any} c
 */
export const llevaLaIA = (c) => !pendiente(c) && !enAtencion(c) && !resuelta(c);

/** El orden en que transcurre un caso, y después el total. */
export const PREDICADOS = {
  'por-atender': pendiente,
  'en-atencion': enAtencion,
  'lleva-ia': llevaLaIA,
  resueltas: resuelta
};

/**
 * Los chats de `lista` que caen en la pestaña `id`. Una pestaña desconocida
 * (o 'todas') devuelve la lista entera: un id viejo guardado en algún lado no
 * puede vaciar la cola.
 *
 * @param {any[]} lista
 * @param {string} id
 */
export function deLaPestana(lista, id) {
  const p = PREDICADOS[/** @type {keyof typeof PREDICADOS} */ (id)];
  return p ? lista.filter(p) : lista;
}

/**
 * Cuántos chats hay en cada pestaña, y si las cuatro primeras cierran contra
 * el total.
 *
 * No cierran cuando un chat tiene dos conversaciones abiertas en estados
 * distintos —una pedida, otra ya tomada—: cuenta en las dos (contrato §4.5,
 * regla 2). No es un error que haya que esconder sino algo que hay que decir,
 * o el número de arriba parece mal sumado.
 *
 * @param {any[]} base
 */
export function contarPestanas(base) {
  const n = {
    'por-atender': 0,
    'en-atencion': 0,
    'lleva-ia': 0,
    resueltas: 0,
    todas: base.length
  };
  for (const c of base) {
    if (pendiente(c)) n['por-atender']++;
    if (enAtencion(c)) n['en-atencion']++;
    if (llevaLaIA(c)) n['lleva-ia']++;
    if (resuelta(c)) n.resueltas++;
  }
  const suma = n['por-atender'] + n['en-atencion'] + n['lleva-ia'] + n.resueltas;
  return { n, suma, cierra: suma === n.todas };
}

/**
 * Horas de espera en palabras para la frase de arriba: «2 h», «45 min»,
 * «3 días». La barra de consola usa «2h» pegado porque es un indicador de
 * 40px; acá es una frase y se lee como tal.
 *
 * @param {number|null|undefined} h
 * @returns {string|null}  null si no se sabe: la frase omite esa parte.
 */
export function esperaEnPalabras(h) {
  if (h === null || h === undefined || !Number.isFinite(h)) return null;
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  // Hasta 48 h en horas: «1 día» por 30 h redondea mal justo donde importa.
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} días`;
}

/**
 * La frase titular de la columna: «20 por atender · la más antigua espera 2 h».
 *
 * Partida en tres para que la pantalla pinte SOLO la cifra: el rojo es del
 * número de trabajo que espera, no de la frase entera.
 *
 * @param {number} pendientes
 * @param {number|null} esperaHoras  `esperaMaximaDe(base)`; null si no se sabe
 * @returns {{ cifra: number|null, texto: string, espera: string|null }}
 */
export function titularDeCola(pendientes, esperaHoras) {
  if (!pendientes) return { cifra: null, texto: 'Nada por atender', espera: null };
  const e = esperaEnPalabras(esperaHoras);
  return {
    cifra: pendientes,
    texto: 'por atender',
    espera: e ? (pendientes === 1 ? `espera ${e}` : `la más antigua espera ${e}`) : null
  };
}
