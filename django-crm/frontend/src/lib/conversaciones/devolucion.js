/**
 * T6 — responder y devolver a la IA, leído desde la pantalla.
 *
 * El motor contesta con tres datos y la pantalla NO puede deducir el desenlace
 * de uno solo:
 *
 *   devuelto_al_asistente   si el control volvió a la IA, de verdad
 *   resultado               qué pasó con la entrega
 *   aviso                   texto para el operador, SOLO cuando hubo rechazo
 *
 * La distinción que este archivo existe para sostener:
 *
 *   rechazado ................................. FALLÓ
 *   incierto / sin_id / aceptado_sin_registro . NO PUDIMOS CONFIRMAR
 *
 * No son lo mismo y no se pueden mostrar igual. «Falló» invita a reintentar, y
 * reintentar un mensaje que sí salió se lo manda al cliente dos veces. Cuando
 * no consta que haya salido, lo honesto es decir que no se sabe y dejar la
 * conversación donde está: en manos de la persona.
 *
 * Tampoco se afirma lo contrario. Un texto tipo «se revirtió sin problema» o
 * «traspaso registrado» diría más de lo que el motor sabe.
 */

/** Lo que el motor puede contestar cuando la entrega no quedó confirmada. */
export const SIN_CONFIRMAR = ['incierto', 'sin_id', 'aceptado_sin_registro'];

const DEVUELTA = {
  estado: 'devuelta',
  tono: 'ok',
  texto: 'La conversación volvió a la IA.'
};

const RECHAZADA = {
  estado: 'fallo',
  tono: 'mal',
  texto: 'El mensaje no salió, así que la conversación sigue a tu cargo.'
};

const SIN_CONFIRMACION = {
  estado: 'no_confirmada',
  tono: 'aviso',
  texto:
    'No podemos confirmar que el mensaje haya salido, así que la conversación ' +
    'sigue a tu cargo. No lo vuelvas a enviar: si salió, el cliente lo recibiría dos veces.'
};

const SIN_RESPUESTA = {
  estado: 'sin_respuesta',
  tono: 'aviso',
  texto:
    'No hubo respuesta del servidor. No sabemos si el mensaje salió ni si la ' +
    'conversación volvió a la IA; por ahora sigue a tu cargo.'
};

/**
 * Traduce la respuesta del motor al estado que la pantalla puede afirmar.
 *
 * @param {{pedida?: boolean, ok?: boolean, datos?: any}} r
 * @returns {{estado: string, tono: string, texto: string}|null}
 *   null cuando no se pidió devolver: este envío no es T6 y no hay nada que decir.
 */
export function estadoDeDevolucion({ pedida = false, ok = false, datos = null } = {}) {
  if (!pedida) return null;
  // Sin respuesta utilizable no se puede afirmar NADA -- ni que salió, ni que
  // no. Es el caso del error de red, y es distinto de un rechazo del canal.
  if (!ok || !datos || typeof datos !== 'object') return SIN_RESPUESTA;
  if (datos.devuelto_al_asistente === true) return DEVUELTA;
  if (datos.resultado === 'rechazado') return RECHAZADA;
  // 'aceptado' sin devolución es raro pero posible: la entrega quedó sellada y
  // el paso 4 no llegó a aplicarse (alguien soltó el control en el medio). No
  // es un fallo de entrega; lo que no ocurrió es la devolución.
  if (datos.resultado === 'aceptado') {
    return {
      estado: 'entregada_sin_devolver',
      tono: 'aviso',
      texto:
        'El mensaje salió, pero la conversación no volvió a la IA. ' +
        'Sigue a tu cargo.'
    };
  }
  return SIN_CONFIRMACION;
}

/**
 * Si conviene ofrecer «Reintentar» para este desenlace.
 *
 * Solo ante un rechazo CONFIRMADO. En todo lo demás el mensaje pudo haber
 * salido, y el reintento se lo mandaría al cliente por segunda vez. Ese fue el
 * motivo de D15, y el motor lo sostiene del otro lado: un reintento con la
 * misma clave no vuelve a entregar.
 */
export function sePuedeReintentar(estado) {
  return estado === 'fallo';
}
