/**
 * ¿Está funcionando el canal de WhatsApp?
 *
 * QUÉ MIDE, Y POR QUÉ ESTO
 * ------------------------
 * De los mensajes enviados en la última hora, cuántos tienen ACUSE de Meta.
 *
 * Un envío que falla se ve solo: la burbuja queda marcada en el hilo, con su
 * botón de reintento, y quien atiende se entera en el momento. Lo que NO se
 * ve es que los envíos salgan bien y los acuses dejen de volver: el servicio
 * parece sano y nadie sabe si al cliente le llegó algo.
 *
 * Esa falla ocurrió y duró DIEZ DÍAS sin que ninguna pantalla la dijera
 * (D17). Este indicador existe por eso, y por eso mide los acuses y no la
 * tasa de error -- que es la que un tablero pondría primero y es la que ya
 * se ve en otro lado.
 *
 * NO PREGUNTA NADA A META. No hay endpoint de salud que consultar, y un
 * "99.99% uptime" inventado sería peor que no decir nada: se mide lo que
 * pasó, no lo que un proveedor afirma de sí mismo.
 *
 * TRES ESTADOS, Y "NO SÉ" ES UNO DE ELLOS
 * ---------------------------------------
 * Sin tráfico no se afirma que el canal esté bien: no hay con qué saberlo.
 * Un cero enviados y un canal sano se ven igual desde acá, y decir "OK" en
 * ese caso es exactamente la afirmación que este archivo existe para no
 * hacer.
 *
 * Vive fuera de Svelte porque es la única forma de probar los estados que el
 * entorno de QA no puede producir: allá `whatsapp_salidas` está vacía, así
 * que en pantalla sólo se ve "sin tráfico". Los otros dos se verifican acá.
 */

/**
 * @param {{enviados:number|null, con_acuse:number|null, fallidos:number|null,
 *          ventana_minutos:number} | null | undefined} m
 * @returns {{estado:'ok'|'sin_acuses'|'sin_trafico'|'no_medido',
 *            etiqueta:string, detalle:string, alerta:boolean} }
 */
export function saludDelCanal(m) {
  // El motor devuelve `enviados: null` cuando no pudo medir. Un null no es un
  // cero: uno dice "no sé" y el otro "no hubo".
  if (!m || m.enviados === null || m.enviados === undefined) {
    return {
      estado: 'no_medido',
      etiqueta: 'WhatsApp ?',
      detalle: 'No se pudo medir el estado del canal.',
      alerta: false
    };
  }

  const ventana = m.ventana_minutos || 60;
  const enviados = Number(m.enviados) || 0;
  const conAcuse = Number(m.con_acuse) || 0;
  const fallidos = Number(m.fallidos) || 0;

  if (enviados === 0) {
    return {
      estado: 'sin_trafico',
      etiqueta: 'WhatsApp —',
      detalle: `No salió ningún mensaje en ${ventana} min: no hay con qué comprobar el canal.`,
      alerta: false
    };
  }

  /* NINGÚN acuse sobre varios envíos es la señal. Con uno o dos envíos no
     alcanza: un acuse puede tardar, y gritar por dos mensajes sin confirmar
     convierte el indicador en ruido. Con cinco o más, que no haya vuelto
     NINGUNO ya no es demora. */
  const MINIMO_PARA_AFIRMAR = 5;
  if (conAcuse === 0 && enviados >= MINIMO_PARA_AFIRMAR) {
    return {
      estado: 'sin_acuses',
      etiqueta: 'WhatsApp sin acuses',
      detalle:
        `${enviados} mensajes salieron en ${ventana} min y no volvió ningún ` +
        `acuse de entrega. Puede que el webhook no esté llegando.`,
      alerta: true
    };
  }

  const conFallos = fallidos > 0 ? ` · ${fallidos} sin poder enviarse` : '';
  return {
    estado: 'ok',
    etiqueta: 'WhatsApp',
    detalle: `${conAcuse} de ${enviados} con acuse en ${ventana} min${conFallos}.`,
    alerta: false
  };
}
