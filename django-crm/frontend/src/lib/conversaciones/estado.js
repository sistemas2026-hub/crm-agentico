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
 * `atendida` mezcla dos cosas: la marca manual, y que exista un mensaje con
 * rol 'humano'. Lo segundo casi no ocurre — 1 de 1.476 mensajes— porque la
 * respuesta de una persona se guarda con rol 'assistant' a propósito (el
 * cliente ve un solo interlocutor, ver agregar_mensaje_humano). Así que en la
 * práctica esto son las que alguien marcó con "Atender" y todavía no cerró.
 *
 * Es el lugar donde va a vivir la asignación real cuando exista.
 * @param {any} c
 */
export const enAtencion = (c) => c.atendida && !resuelta(c);
