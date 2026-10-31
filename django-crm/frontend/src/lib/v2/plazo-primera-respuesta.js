/**
 * Como esta el reloj de la PRIMERA RESPUESTA de un ticket.
 *
 * La misma lectura que hace la cola (routes/(app)/tickets/+page.svelte,
 * `responsePressure`), sacada a una funcion pura para que el detalle no tenga
 * una segunda version de la regla. La lista todavia usa la suya; conectarla
 * aca es un cambio aparte.
 *
 * EL VENCIMIENTO NO SE RECALCULA. `first_response_deadline` llega del
 * servidor ya caminado por el calendario laboral de la empresa y corrido por
 * el tiempo que el ticket estuvo esperando al cliente. Volver a sacarlo de
 * `opened_at + horas` pondria en la misma pantalla una segunda respuesta,
 * calladamente distinta. Las horas (`first_response_hours`) solo se muestran
 * como "Plazo de N h", nunca se usan para calcular.
 *
 * Tonos: rust al pasar el 100 %, clay desde el 75 %, ember (indigo) antes, y
 * moss cuando ya se respondio. Slate cuando no hay nada que medir (en pausa,
 * sin objetivo, cerrado sin respuesta).
 *
 * @typedef {'respondida'|'vencida'|'corriendo'|'pausada'|'sin_objetivo'|'cerrada_sin_respuesta'} EstadoPlazo
 * @typedef {'moss'|'rust'|'clay'|'ember'|'slate'} TonoPlazo
 * @typedef {{
 *   estado: EstadoPlazo,
 *   texto: string,
 *   pct: number | null,
 *   tono: TonoPlazo,
 *   plazo: string
 * }} Plazo
 */

/**
 * Una duracion en minutos, corta y en español.
 * @param {number} minutos
 */
export function duracionCorta(minutos) {
  const n = Math.max(0, Math.round(minutos));
  if (n < 1) return 'menos de 1 min';
  if (n < 60) return `${n} min`;
  if (n < 1440) return `${Math.round(n / 60)} h`;
  const d = Math.round(n / 1440);
  return `${d} ${d === 1 ? 'día' : 'días'}`;
}

/** @param {any} v */
const ms = (v) => {
  const t = v ? new Date(v).getTime() : NaN;
  return Number.isFinite(t) ? t : null;
};

/**
 * @param {{
 *   opened_at?: string | null,
 *   first_response_at?: string | null,
 *   first_response_deadline?: string | null,
 *   first_response_hours?: number | null,
 *   first_response_breached?: boolean,
 *   paused_at?: string | null,
 *   is_open?: boolean
 * }} t
 * @param {number} [ahora]
 * @returns {Plazo}
 */
export function plazoPrimeraRespuesta(t, ahora = Date.now()) {
  const horas = Number(t?.first_response_hours);
  const plazo = Number.isFinite(horas) && horas > 0 ? `Plazo de ${horas} h` : '';
  const abierto = ms(t?.opened_at);
  const respondido = ms(t?.first_response_at);
  const vence = ms(t?.first_response_deadline);

  if (respondido !== null) {
    const tardo = abierto !== null ? (respondido - abierto) / 6e4 : null;
    return {
      estado: 'respondida',
      texto: tardo !== null
        ? `Respondida a los ${duracionCorta(tardo)}${t?.first_response_breached ? ', fuera de plazo' : ''}`
        : 'Respondida',
      pct: 100,
      tono: 'moss',
      plazo
    };
  }

  if (t?.is_open === false) {
    return { estado: 'cerrada_sin_respuesta', texto: 'Se cerró sin primera respuesta', pct: null, tono: 'slate', plazo };
  }

  // Esperando al cliente: el servidor corre el vencimiento por este tiempo,
  // asi que un "vence en" ahora seria un numero que se mueve solo.
  if (t?.paused_at) {
    return {
      estado: 'pausada',
      texto: 'Primera respuesta en pausa: esperando al cliente',
      pct: null,
      tono: 'slate',
      plazo
    };
  }

  if (vence === null) {
    return { estado: 'sin_objetivo', texto: 'Sin plazo de primera respuesta', pct: null, tono: 'slate', plazo };
  }

  if (ahora >= vence) {
    return {
      estado: 'vencida',
      texto: `Primera respuesta vencida hace ${duracionCorta((ahora - vence) / 6e4)}`,
      pct: 100,
      tono: 'rust',
      plazo
    };
  }

  const total = abierto !== null ? vence - abierto : 0;
  const pct = total > 0 ? Math.max(0, Math.min(100, Math.round(((ahora - abierto) / total) * 100))) : 0;
  return {
    estado: 'corriendo',
    texto: `Vence en ${duracionCorta((vence - ahora) / 6e4)}`,
    pct,
    tono: pct >= 100 ? 'rust' : pct >= 75 ? 'clay' : 'ember',
    plazo
  };
}
