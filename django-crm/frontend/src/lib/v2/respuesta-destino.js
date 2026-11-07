/**
 * A DONDE VA lo que se escribe en la caja de respuesta de un ticket.
 *
 * EL DEFECTO QUE ESTO CIERRA (24/10/2026). La caja decia "Responder al
 * cliente por donde escribió…" en TODOS los tickets. En uno sin chat de
 * WhatsApp detras --cargado a mano, o importado del sistema del ISP-- el motor
 * contesta 404 `sin_conversacion`, la respuesta queda guardada en el ticket y
 * al cliente no le llega nada. Nadie lo decia: quien respondia daba al
 * cliente por avisado.
 *
 * La señal de "hay conversacion" es la MISMA que usa el envio: el motor busca
 * la conversacion del caso con `conversacion_de_caso` tanto en
 * `GET /conversaciones/por-caso/{id}` (lo que carga la pantalla) como en
 * `POST /casos/{id}/mensajes` (lo que entrega). Si la primera no encontro
 * conversacion, la segunda tampoco la va a encontrar.
 *
 * Mientras esa lectura no llego, no se afirma ninguna de las dos cosas: decir
 * "sale por WhatsApp" de un ticket que no tiene chat es el mismo defecto de
 * antes, y decir "no le llega" de uno que si lo tiene asusta sin motivo.
 *
 * @typedef {'nota'|'chat'|'sin_chat'|'comprobando'|'no_se_pudo'} ClaveDestino
 * @typedef {'neutro'|'accion'|'atencion'} TonoDestino
 * @typedef {{
 *   clave: ClaveDestino,
 *   tono: TonoDestino,
 *   aviso: string,
 *   boton: string,
 *   primario: boolean,
 *   ofreceDevolver: boolean
 * }} Destino
 */

/**
 * El nombre del canal tal como lo declara el despliegue, legible. No se fija
 * 'WhatsApp' a ciegas: la misma instancia distingue el canal de produccion del
 * simulador, y poner siempre 'WhatsApp' haria pasar una prueba por un cliente.
 *
 * @param {string | null | undefined} canal
 */
export function nombreDelCanal(canal) {
  const limpio = String(canal ?? '').replace(/[-_]/g, ' ').trim();
  if (!limpio || limpio.toLowerCase() === 'whatsapp') return 'WhatsApp';
  return limpio[0].toUpperCase() + limpio.slice(1);
}

/**
 * @param {{
 *   interna: boolean,
 *   hayConversacion: boolean | null | undefined | 'no_se_pudo',
 *   cliente?: string | null,
 *   canal?: string | null
 * }} entrada
 *   `hayConversacion`: true = el motor encontro el chat del caso; false = el
 *   motor contesto y no hay chat; null/undefined = todavia no se sabe;
 *   'no_se_pudo' = la lectura fallo (motor caido, sin configurar).
 * @returns {Destino}
 */
export function destinoDeLaRespuesta({ interna, hayConversacion, cliente, canal }) {
  if (interna) {
    return {
      clave: 'nota',
      tono: 'neutro',
      aviso: 'Solo la ve el equipo. No le llega al cliente ni cuenta como primera respuesta.',
      boton: 'Guardar nota',
      primario: false,
      ofreceDevolver: false
    };
  }

  if (hayConversacion === true) {
    const nombre = String(cliente ?? '').trim();
    const medio = nombreDelCanal(canal);
    return {
      clave: 'chat',
      tono: 'accion',
      aviso: `Sale por ${medio} ${nombre ? `a ${nombre}` : 'al cliente'}.`,
      boton: `Enviar por ${medio}`,
      primario: true,
      ofreceDevolver: true
    };
  }

  if (hayConversacion === false) {
    return {
      clave: 'sin_chat',
      tono: 'atencion',
      aviso:
        'Este ticket no tiene un chat de WhatsApp: el cliente no va a recibir este mensaje. ' +
        'Queda guardado en el ticket. Para avisarle, llamalo o escribile por otro medio.',
      boton: 'Guardar respuesta',
      primario: false,
      ofreceDevolver: false
    };
  }

  if (hayConversacion === 'no_se_pudo') {
    // El envio igual pregunta al motor: si el chat existe, sale. Lo unico
    // que no se puede es prometerlo de antemano.
    return {
      clave: 'no_se_pudo',
      tono: 'neutro',
      aviso:
        'No se pudo comprobar si este ticket tiene un chat de WhatsApp. Si lo tiene, la ' +
        'respuesta sale por ahí; si no, queda guardada en el ticket y el cliente no la recibe.',
      boton: 'Enviar respuesta',
      primario: false,
      ofreceDevolver: false
    };
  }

  return {
    clave: 'comprobando',
    tono: 'neutro',
    aviso: 'Comprobando si hay un chat de WhatsApp…',
    boton: 'Enviar respuesta',
    primario: false,
    ofreceDevolver: false
  };
}
