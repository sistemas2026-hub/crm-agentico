/**
 * ============================================================================
 *  CÓMO QUEDÓ CADA FOTO, EN UNA LÍNEA  --  17/11/2026
 * ============================================================================
 * El panel mostraba, por cada foto, las instrucciones completas de la
 * plantilla más la prosa entera del modelo más sus tres líneas de marca
 * (`CATALOGO:`, `MUESTRA:`, `ATENCION:`). Ocho renglones por foto, cuatro
 * fotos por orden: el supervisor leía treinta renglones para enterarse de
 * que no había nada que hacer.
 *
 * El usuario, el 17/11/2026: «que no muestre ese texto, que mejor muestre si
 * pasa, y cuando no pase, por qué».
 *
 * NO SE AGREGA NINGÚN DATO NUEVO. Los cuatro que hacen falta ya viajaban en
 * la respuesta (`revision_del_cierre._evidencias_para_revisar`); lo que
 * cambia es que se componen en una línea en vez de volcarse crudos.
 *
 * SILENCIO NO ES APROBACIÓN, Y ESA ES LA REGLA QUE ORDENA TODO LO DEMÁS
 * ---------------------------------------------------------------------
 * Si no hay análisis, `ok` es `null` y la línea no sale: ni ✓ ni ⚠. La
 * visión puede estar apagada para esa empresa, o la foto puede no haberse
 * podido mirar, y un ✓ ahí sería la pantalla afirmando una revisión que no
 * pasó. Ya existía como guarda del componente («sin análisis no inventa un
 * visto bueno»), y esto la hereda en vez de reabrirla.
 *
 * Y UN ✓ NO DICE «LA FOTO ESTÁ BIEN»
 * -----------------------------------
 * Dice «sin observaciones». El modelo no afirma que la foto sirva: afirma
 * que no vio nada que llame la atención. Es la misma distinción del
 * encabezado de `campo/inspeccion_visual.py` (31/10/2026) --la IA puede
 * pedir atención, nunca aprobar ni negar-- aplicada a cómo se redacta.
 * ============================================================================
 */

/**
 * @param {{evidencia_id?: string|null, analisis?: string,
 *          pide_atencion?: boolean, muestra_lo_pedido?: boolean|null,
 *          instrucciones?: string}} e
 * @returns {{ok: boolean|null, texto: string}}
 *   ok `true` sin observaciones · `false` hay algo que mirar · `null` no se
 *   puede decir nada, y entonces no se dice.
 */
export function comoQuedoLaFoto(e) {
  if (!e?.evidencia_id) return { ok: false, texto: 'No llegó.' };

  //  Sin análisis no hay nada que afirmar. VA ANTES QUE TODO LO DEMÁS: los
  //  otros campos vienen en su valor por defecto (`false`, `null`) cuando no
  //  hubo mirada, y leerlos como veredicto convertiría la ausencia en un ✓.
  if (!e.analisis) return { ok: null, texto: '' };

  //  PRIMERO «NO ES LO QUE SE PIDIÓ», y no es un orden arbitrario: son dos
  //  problemas con dos arreglos distintos. «Hay un televisor donde pedían el
  //  router» se arregla sacando otra foto; «se ve un cable suelto» se
  //  arregla volviendo a la casa. El componente ya las separaba y acá se
  //  elige la más específica para la línea corta.
  if (e.muestra_lo_pedido === false) {
    return { ok: false, texto: 'No es lo que se pidió.' };
  }
  if (e.pide_atencion) return { ok: false, texto: 'Pide una mirada.' };

  //  `null` ES «NO SE SABE», NUNCA «ESTÁ BIEN» --borrosa, oscura, un primer
  //  plano del que no se deduce qué equipo es--. Solo se dice cuando la
  //  plantilla DECLARÓ qué tenía que mostrar: sin instrucciones el modelo no
  //  escribe esa línea (regla 12 de `nucleo/canales/vision.py`), y marcar
  //  esa ausencia pondría en duda toda foto de toda plantilla que no las
  //  tenga -- un interrogante permanente que la gente aprende a ignorar.
  if (e.muestra_lo_pedido === null && e.instrucciones) {
    return { ok: false, texto: 'No se pudo determinar si muestra lo que se pedía.' };
  }

  return { ok: true, texto: 'Sin observaciones.' };
}
