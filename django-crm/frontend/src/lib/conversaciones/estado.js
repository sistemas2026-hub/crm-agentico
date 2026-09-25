/**
 * En qué estado está una conversación de la bandeja.
 *
 * POR QUÉ ESTO ES UN MÓDULO Y NO TRES FUNCIONES EN CADA PANTALLA
 * -------------------------------------------------------------
 * Estaban duplicadas. El índice traía su propia copia de `pendiente` con el
 * comentario "mismo criterio que el filtro de la barra lateral" — y el
 * 07/09/2026 dejó de serlo: la cabecera decía "41 por atender" y el panel
 * vacío, en la misma pantalla, "hay 44 esperando a una persona".
 *
 * No lo detectó ningún test. `pnpm check` no lo ve (los dos lados compilan),
 * la guarda que abre las pantallas tampoco (la página renderiza perfecto con
 * dos números distintos). Se vio abriendo la pantalla y mirándola.
 *
 * Un comentario que dice "igual que aquel otro" no mantiene nada igual.
 */

/**
 * Pide algo de una persona, y todavía nadie del equipo escribió.
 *
 * Dos formas de llegar acá, y la segunda es la que importa:
 *
 *  - Escalada de verdad: hay caso y ticket detrás.
 *  - Sin escalar pero marcada: el evaluador se cayó y NO se pudo decidir si
 *    correspondía escalar (NO_DETERMINADO, ver
 *    nucleo/seguimiento/estado_escalada.py). No se inventa una escalada
 *    —sería afirmar un traspaso que no ocurrió y pausaría al bot— pero la
 *    conversación tiene que verse igual, o el pedido del cliente se pierde en
 *    silencio, que es peor.
 *
 * @param {any} c
 */
export const pendiente = (c) =>
  (c.escalada_a_humano || c.necesita_atencion_humana) &&
  !c.atendida &&
  // Si alguien se la adjudico, ya no espera a "una persona": espera a ESA
  // persona, y eso es la pestaña de al lado.
  !c.tomada_por &&
  // Una conversación cerrada no espera a nadie. Se contaban igual, y eran 28
  // de las 155 que la cabecera decía que estaban esperando.
  c.estado !== 'cerrada';

/**
 * Ya terminó. SOLO `estado === 'cerrada'`, y esto tiene historia.
 *
 * La primera versión decía `cerrada || atendida_manual`. Parecía razonable —
 * `atendida_manual` era, durante meses, la única señal de "me hice cargo de
 * esto" — pero colapsa los dos botones en uno, porque son justo lo que los
 * distingue (nucleo/persistencia/db.py):
 *
 *   marcar_atendida()       atendida_manual = true,  sigue ABIERTA
 *   resolver_conversacion() atendida_manual = true,  estado = 'cerrada'
 *
 * Con la definición vieja, darle a "Atender" mandaba la conversación directo
 * a "Resueltas" y dejaba "En atención" vacía POR CONSTRUCCIÓN: medido el
 * 07/09/2026, 13 atendidas, 12 de ellas por `atendida_manual`, y la pestaña
 * marcaba 0. Una pestaña que no puede llenarse nunca es peor que no tenerla.
 *
 * @param {any} c
 */
export const resuelta = (c) => c.estado === 'cerrada';

/**
 * Alguien se hizo cargo y el caso sigue vivo.
 *
 * `tomada_por` y NO `atendida_manual`. La primera versión usaba la segunda, y
 * estaba mal de una forma que no se veía: `atendida_manual` significa
 * "resuelto por teléfono, en persona o por otro canal" —lo dice el comentario
 * de su propia columna— y habilita dos cierres automáticos en el motor:
 *
 *   db.py:625  un "ok, gracias" del cliente CIERRA el caso, pero solo si
 *              alguien ya lo atendió
 *   db.py:799  el barrido por plazo vencido cierra SOLO lo ya atendido
 *
 * Con esa definición, pulsar "Atender" para decir "me hago cargo" dejaba el
 * caso cerrable por un agradecimiento del cliente y por el barrido. Y
 * marcar_atendida() no tiene desmarcar, a propósito.
 *
 * Tomar es otra cosa y es reversible. Se sigue contando el caso donde una
 * persona ya escribió en el hilo: eso también es hacerse cargo.
 * @param {any} c
 */
export const enAtencion = (c) => (!!c.tomada_por || c.atendida) && !resuelta(c);
