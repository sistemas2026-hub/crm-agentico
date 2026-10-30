/**
 * ¿PODEMOS CONFIAR EN LO QUE ESTA PANTALLA MUESTRA?
 *
 * Decide entre tres estados, y el tercero es el que no existía:
 *
 *   actividad        hay una instrucción operativa vigente, con su evento
 *   reposo           no hay actividad Y los datos están al día
 *   sin_informacion  no podemos confirmar que los datos estén al día
 *
 * POR QUÉ HACE FALTA
 * Hasta ahora un agente sin eventos se veía igual que uno cuyo backend dejó de
 * responder: los dos, quietos. Eso convierte la quietud en una afirmación
 * falsa — «este agente no tiene trabajo» cuando lo cierto es «no tengo ni idea
 * de lo que hace este agente».
 *
 * Es la misma regla por la que el motor NO emite el estado `offline`:
 * confundir «sin datos» con «caído» hace que la pantalla avise de una avería
 * que no existe. Acá el error sería el simétrico y peor: callar una que sí.
 *
 * POR QUÉ `retraso_s` NO ALCANZA, aunque sea el dato más preciso
 * `retraso_s` lo calcula el backend y viaja CON la respuesta. Si el backend
 * deja de responder, no llega ningún `retraso_s` — llega nada. Un indicador
 * que solo mirara ese campo se quedaría mostrando el último valor bueno justo
 * cuando más importa que avise.
 *
 * Por eso la frescura se mide con CUATRO señales, y tres de ellas son del
 * cliente, que es quien sí puede notar un silencio:
 *
 *   1. hace cuánto fue la última respuesta correcta   (silencio)
 *   2. si el último intento falló                      (error)
 *   3. si nunca hubo una respuesta                     (arranque)
 *   4. el retraso que el backend declara               (retraso)
 */

/**
 * Umbrales, en segundos. Se declaran acá y no se esparcen por la pantalla,
 * porque son un criterio de producto y no un detalle de implementación.
 */
export const UMBRALES = {
  /** Sin una respuesta correcta en este tiempo, dejamos de confiar.
   *  Son ~3 sondeos de 12 s: uno perdido es ruido, tres son un silencio. */
  silencio_s: 40,
  /** Retraso del flujo declarado por el backend a partir del cual la pantalla
   *  deja de prometer frescura. Una transacción larga retiene el cursor, y el
   *  peor caso NO está acotado: `idle_in_transaction_session_timeout` solo
   *  corta sesiones OCIOSAS, no una que sigue ejecutando o esperando un lock. */
  retraso_s: 30
};

/**
 * El veredicto sobre los datos, con su motivo.
 *
 * @param {{ultimaRespuestaOk?: number|null, ultimoFallo?: number|null,
 *          retraso_s?: number|null, ahora?: number,
 *          umbrales?: {silencio_s:number, retraso_s:number}}} señales
 */
export function frescura(señales = {}) {
  const u = { ...UMBRALES, ...(señales.umbrales || {}) };
  const ahora = señales.ahora ?? Date.now();
  const ok = señales.ultimaRespuestaOk ?? null;
  const fallo = señales.ultimoFallo ?? null;
  const retraso = señales.retraso_s ?? null;

  // 1 · ARRANQUE. Antes de la primera respuesta no se sabe nada, y eso es
  //     «sin información», no «reposo». La pantalla no nace diciendo que todo
  //     está tranquilo: nace diciendo que todavía no sabe.
  if (ok == null) {
    return { confiable: false, motivo: 'sin_lectura',
             detalle: 'todavía no hubo ninguna respuesta', silencio_s: null };
  }

  const silencio_s = Math.max(0, Math.round((ahora - ok) / 1000));

  // 2 · SILENCIO. El cliente es el único que puede notarlo: si el backend no
  //     contesta, no manda un aviso de que no contesta.
  if (silencio_s >= u.silencio_s) {
    return { confiable: false, motivo: 'silencio',
             detalle: `sin respuesta hace ${silencio_s}s`, silencio_s };
  }

  // 3 · EL ÚLTIMO INTENTO FALLÓ. Aunque hace poco hubiera uno bueno: lo que
  //     importa es si lo ÚLTIMO que sabemos es un error.
  if (fallo != null && (ok == null || fallo > ok)) {
    return { confiable: false, motivo: 'error',
             detalle: 'la última lectura falló', silencio_s };
  }

  // 4 · EL BACKEND DECLARA RETRASO. Llega al día pero avisa de que el flujo
  //     viene atrasado: una transacción en vuelo retiene el cursor.
  if (retraso != null && retraso >= u.retraso_s) {
    return { confiable: false, motivo: 'retraso',
             detalle: `el flujo viene ${Math.round(retraso)}s atrasado`,
             silencio_s };
  }

  return { confiable: true, motivo: 'al_dia', detalle: null, silencio_s };
}

/**
 * El estado que se le pinta a un agente, con la frescura por delante.
 *
 * «Sin información» GANA SIEMPRE. Mostrar una actividad vieja como si fuera
 * actual es peor que no mostrar nada: lo segundo se nota, lo primero no.
 *
 * Y «reposo» NO significa «disponible». Significa «no hay ninguna actividad
 * vigente y los datos están al día». Que el agente pueda atender algo es otra
 * pregunta, y esta pantalla no la responde.
 */
export function estadoVisible(instruccion, veredicto) {
  if (!veredicto || !veredicto.confiable) {
    return { estado: 'sin_informacion',
             motivo: veredicto?.motivo ?? 'sin_lectura',
             detalle: veredicto?.detalle ?? null,
             // Procedencia 'ambiente': no saber NO es una actividad operativa
             // y no puede acabar en el historial como si lo fuera.
             procedencia: 'ambiente' };
  }
  if (instruccion && instruccion.tipo && instruccion.tipo !== 'reposo') {
    return { estado: 'actividad', tipo: instruccion.tipo,
             etiqueta: instruccion.etiqueta,
             procedencia: instruccion.procedencia };
  }
  return { estado: 'reposo', motivo: 'sin_actividad_vigente',
           detalle: null, procedencia: 'ambiente' };
}
