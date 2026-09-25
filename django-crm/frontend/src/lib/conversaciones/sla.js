/**
 * El plazo de toma: cuánto puede esperar una conversación escalada antes de
 * que alguien la tome.
 *
 * QUÉ MIDE, Y QUÉ NO
 * ------------------
 * Mide UNA sola cosa: que alguien escribió, el asistente lo pasó a una
 * persona, y ninguna persona lo tomó todavía. No mide cuánto tarda en
 * resolverse -- eso depende del caso, y convertirlo en un número obliga a
 * inventar categorías que nadie midió.
 *
 * POR ESO SÓLO APLICA A LAS QUE NO TIENEN DUEÑO. Una conversación que alguien
 * ya tomó no está incumpliendo nada aunque lleve tres horas: está siendo
 * atendida. Dibujarle un reloj en rojo sería marcar como incumplimiento el
 * trabajo normal, que es exactamente cómo una alarma deja de significar algo.
 *
 * EL OBJETIVO SALE DE LA CONFIG DEL TENANT (`sla_toma_minutos`), nunca de acá:
 * un ISP con guardia 24 h y uno que atiende de 8 a 18 no toleran lo mismo.
 * Sin objetivo definido (0) esto devuelve null y la pantalla no dibuja nada --
 * no se inventa un plazo por defecto para tener algo que mostrar.
 *
 * Vive fuera de Svelte y en su propio archivo para poder probarlo: es una
 * cuenta que decide de qué color se ve una fila, y ese tipo de cuenta es
 * justo la que se rompe sin que se note mirando la pantalla.
 */

/** El mismo criterio que usa la cola: espera desde la necesidad ACTUAL. */
export function esperandoDesde(/** @type {any} */ c) {
  return c?.esperando_desde || c?.escalada_en || null;
}

/**
 * Cuánto falta (o cuánto sobra) para el plazo de toma.
 *
 * @param {any} c            la conversación, tal como la manda el motor
 * @param {number} objetivoMinutos  `sla_toma_minutos` del tenant; 0 = sin objetivo
 * @param {number} ahora     epoch ms; se pasa para que la prueba lo fije
 * @returns {{restanMinutos: number, vencido: boolean, porVencer: boolean,
 *            objetivoMinutos: number} | null}
 */
export function plazoDeToma(c, objetivoMinutos, ahora = Date.now()) {
  const objetivo = Number(objetivoMinutos) || 0;
  if (objetivo <= 0) return null;

  // Sólo las que esperan a una persona Y no tiene dueño. `asignada_a_usuario_id`
  // es la asignación durable de Dexter, no el dueño del ticket del CRM (D28).
  if (!c?.escalada_a_humano) return null;
  if (c?.asignada_a_usuario_id) return null;
  if (c?.estado === 'cerrada') return null;

  const desde = esperandoDesde(c);
  if (!desde) return null;
  const t = new Date(desde).getTime();
  if (Number.isNaN(t)) return null;

  const esperadosMin = (ahora - t) / 60000;
  const restan = objetivo - esperadosMin;

  return {
    restanMinutos: Math.round(restan),
    vencido: restan <= 0,
    /* "Por vencer" empieza al último TERCIO, no en un número fijo de minutos:
       con un objetivo de 15 min avisa cuando quedan 5, y con uno de 4 h
       cuando quedan 80. Un aviso "a 5 minutos del final" no significa lo
       mismo en los dos.

       Era un cuarto y lo corrigió la prueba: en un plazo de 15 minutos, el
       último cuarto son 3,75 -- avisar ahí es avisar cuando ya no hay tiempo
       de hacer nada, que es lo mismo que no avisar. */
    porVencer: restan > 0 && restan <= objetivo / 3,
    objetivoMinutos: objetivo
  };
}

/** `-3` -> "+3m" (vencido hace 3), `7` -> "7m". Sin signo negativo a la vista:
    "vencido" ya lo dice la palabra, y un menos delante se lee como un error. */
export function textoDePlazo(/** @type {ReturnType<typeof plazoDeToma>} */ p) {
  if (!p) return '';
  const m = Math.abs(p.restanMinutos);
  const cuerpo = m >= 120 ? `${Math.round(m / 60)}h` : `${m}m`;
  return p.vencido ? `+${cuerpo}` : cuerpo;
}
