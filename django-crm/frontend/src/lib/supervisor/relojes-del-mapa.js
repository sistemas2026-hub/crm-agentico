/**
 * CUÁNDO SE MIRÓ, Y CUÁNDO REPORTÓ CADA UNO (05/11/2026).
 *
 * Pedido del usuario: «el supervisor debe consultar las ubicaciones en un
 * tiempo no tan largo, y abajo del mapa me gustaría ver el log de cuándo
 * verificó las ubicaciones, con su fecha y hora».
 *
 * SON DOS RELOJES DISTINTOS Y LA PANTALLA TIENE QUE MOSTRAR LOS DOS, porque
 * fallan por separado y el supervisor no puede distinguirlos de otra forma:
 *
 *   1. CUÁNDO PREGUNTÓ LA PANTALLA. Cada 15 s. Si este se congela, el
 *      problema es el navegador o la red del supervisor: lo que ve es viejo
 *      aunque los técnicos estén reportando perfecto.
 *   2. CUÁNDO REPORTÓ CADA TELÉFONO. Cada 90 s manda la app. Si este se
 *      congela para UNA cuadrilla, el problema es ese teléfono.
 *
 * Con un solo reloj los dos fallos se ven iguales --«el mapa no se mueve»--
 * y llevan a llamar a la persona equivocada.
 *
 * LA HORA VA EN AMERICA/BOGOTÁ, FIJA. `medida_en` llega con su offset y el
 * navegador formatearía en la zona del equipo: un supervisor con el reloj del
 * portátil en otra zona leería una hora que no es la de la calle. Es la misma
 * regla que el resto del proyecto («horas siempre en America/Bogotá al
 * reportar»), aplicada acá porque esta hora se compara contra la del celular
 * del supervisor para decidir si llamar a alguien.
 */

/** La zona de la operación. Ver el encabezado: no se toma la del navegador. */
export const ZONA = 'America/Bogota';

/**
 * La hora de un instante, corta, en la zona de la operación.
 *
 * Devuelve '' para lo que no es una fecha, en vez de 'Invalid Date': esto se
 * pinta en pantalla y una cadena vacía se lee como «no hay dato», que es lo
 * que pasó.
 *
 * @param {string | number | Date | null | undefined} cuando
 * @param {boolean} [conSegundos]
 */
export function horaCorta(cuando, conSegundos = false) {
  if (cuando === null || cuando === undefined || cuando === '') return '';
  const d = cuando instanceof Date ? cuando : new Date(cuando);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('es-CO', {
    timeZone: ZONA,
    hour: '2-digit',
    minute: '2-digit',
    ...(conSegundos ? { second: '2-digit' } : {}),
    hour12: false
  });
}

/**
 * Hace cuánto, en palabras cortas.
 *
 * SE REDONDEA HACIA ABAJO A PROPÓSITO: «hace 1 min» para 119 segundos dice
 * menos de lo real y eso es lo seguro acá. Lo contrario --redondear hacia
 * arriba-- haría que un dato de 31 segundos se anuncie como «hace 1 min» y el
 * supervisor crea que la pantalla está más atrasada de lo que está.
 *
 * @param {number} segundos
 */
export function desdeHace(segundos) {
  const s = Math.max(0, Math.floor(Number(segundos) || 0));
  if (s < 60) return `hace ${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `hace ${m} min`;
  const h = Math.floor(m / 60);
  return `hace ${h} h ${m % 60} min`;
}

/**
 * Una fila por cuadrilla para la lista de abajo del mapa.
 *
 * LAS QUE NO REPORTARON TAMBIÉN SALEN, y es la mitad del valor de esta lista:
 * una cuadrilla sin señal desaparece del mapa --no se le inventa un pin-- y
 * sin esta fila desaparecería también de la pantalla. El supervisor no puede
 * echar de menos lo que no ve.
 *
 * `centrable` dice si el botón hace algo. Una fila sin posición se muestra
 * igual pero su botón va deshabilitado: un botón que no responde al clic, sin
 * explicación, se lee como pantalla rota.
 *
 * @param {any[]} cuadrillas
 */
export function filasDeSeguimiento(cuadrillas) {
  return (cuadrillas ?? []).map((c) => {
    const p = c?.posicion ?? null;
    return {
      jornada: c?.jornada ?? '',
      cuadrilla: c?.cuadrilla ?? '',
      centrable: Boolean(p),
      fresca: Boolean(p?.fresca),
      //  La hora del reporte, no la de ahora: es el dato que el supervisor
      //  compara contra su propio reloj.
      hora: p ? horaCorta(p.medida_en) : '',
      minutos: p ? Number(p.minutos ?? 0) : null,
      de: p?.de ?? '',
      //  Qué decir en la fila. Sin posición no se dice «hace N min» de nada.
      dice: p
        ? `${horaCorta(p.medida_en)} · ${desdeHace(Number(p.minutos ?? 0) * 60)}`
        : 'sin señal'
    };
  });
}
