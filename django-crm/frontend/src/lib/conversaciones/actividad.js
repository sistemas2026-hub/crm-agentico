/**
 * El registro del relevo, contado en palabras (fase 1.6).
 *
 * El motor guarda un evento por transición: un tipo, quién actuó y los datos
 * que el contrato declara para ese tipo. Acá se convierte en una línea que se
 * pueda leer de un vistazo.
 *
 * Dos reglas que no son obvias:
 *
 * 1. **No se infiere quién actuó.** El evento trae `actor_tipo` y, si fue una
 *    persona, `actor_nombre` (la base lo exige: un evento de operador dice
 *    quién fue). Cuando no consta, se dice que no consta — nunca se atribuye
 *    al equipo ni a la IA para completar la frase. Es la misma regla que D30
 *    impuso en el hilo.
 *
 * 2. **Un tipo desconocido no se descarta ni se inventa.** El motor puede
 *    escribir tipos que esta pantalla todavía no conoce (el `check` de la base
 *    declara diecinueve). Se muestra la línea con el tipo crudo en vez de
 *    esconder un hecho que sí ocurrió.
 */

/** Quién actuó, sin rellenar lo que no consta. */
export function actorDe(ev) {
  const nombre = (ev?.actor_nombre ?? '').trim();
  switch (ev?.actor_tipo) {
    case 'operador':
      return nombre || 'Alguien del equipo';
    case 'ia':
      return 'Dexter IA';
    case 'sistema':
      return 'El sistema';
    case 'cliente':
      return 'El cliente';
    default:
      return 'Sin registro';
  }
}

/**
 * Qué pasó. Devuelve `{ texto, detalle, tono }`:
 *   texto    la frase principal
 *   detalle  lo que agregan los datos del evento, o null
 *   tono     'ia' | 'humano' | 'aviso' | 'neutro'
 */
export function loQuePaso(ev) {
  const d = ev?.datos ?? {};
  const quien = actorDe(ev);
  const motivo = (d.motivo ?? d.motivo_texto ?? '').toString().trim();

  switch (ev?.tipo) {
    case 'escalada':
      return { texto: 'Pasó a manos del equipo', detalle: motivo || null, tono: 'aviso' };
    case 'intervencion':
      return { texto: `${quien} intervino la conversación`, detalle: motivo || null, tono: 'humano' };
    case 'tomada':
      return { texto: `${quien} la tomó`, detalle: null, tono: 'humano' };
    case 'soltada':
      return { texto: `${quien} la soltó`, detalle: null, tono: 'neutro' };
    case 'reasignada': {
      const de = (d.anterior_nombre ?? '').trim();
      const a = (d.nuevo_nombre ?? '').trim();
      return {
        texto: a ? `Reasignada a ${a}` : 'Reasignada',
        // "de quién" sólo si consta: una reasignación desde "sin asignar" no
        // tiene anterior, y escribir "de nadie" seria raro y falso.
        detalle: [de ? `antes la llevaba ${de}` : null, motivo || null]
          .filter(Boolean).join(' · ') || null,
        tono: 'humano'
      };
    }
    case 'devolucion_solicitada':
      return { texto: `${quien} respondió y pidió devolverla a la IA`, detalle: null, tono: 'neutro' };
    case 'devuelta_a_ia':
      return { texto: 'Volvió a manos de la IA', detalle: null, tono: 'ia' };
    case 'devolucion_fallida':
      // El desenlace REAL, no el nombre del evento: 'devolucion_fallida' con
      // resultado 'incierto' significa que no se pudo confirmar, no que falló.
      return {
        texto: d.resultado === 'rechazado'
          ? 'No volvió a la IA: el mensaje no salió'
          : 'No volvió a la IA: no se pudo confirmar que el mensaje saliera',
        detalle: null,
        tono: 'aviso'
      };
    case 'pendiente_interno_abierto':
      return { texto: 'Quedó esperando algo interno', detalle: motivo || null, tono: 'aviso' };
    case 'pendiente_interno_cerrado':
      return { texto: 'Se resolvió lo que estaba pendiente', detalle: null, tono: 'neutro' };
    case 'evaluacion_revisada':
      return { texto: `${quien} revisó la evaluación`, detalle: null, tono: 'neutro' };
    case 'caso_externo_cerrado':
      return { texto: 'El caso se cerró en el sistema externo', detalle: null, tono: 'aviso' };
    case 'cerrada':
      return { texto: 'Conversación cerrada', detalle: null, tono: 'neutro' };
    case 'accion_aprobada':
      return { texto: `${quien} aprobó una acción`, detalle: null, tono: 'humano' };
    case 'accion_rechazada':
      return { texto: `${quien} rechazó una acción`, detalle: null, tono: 'aviso' };
    case 'accion_vencida':
      return { texto: 'Una acción propuesta venció sin respuesta', detalle: null, tono: 'aviso' };
    case 'accion_cancelada':
      return { texto: 'Se canceló una acción propuesta', detalle: null, tono: 'neutro' };
    case 'accion_propuesta_duplicada':
      return { texto: 'Se propuso una acción que ya estaba propuesta', detalle: null, tono: 'neutro' };
    case 'accion_desconocida':
      return { texto: 'Se propuso una acción que el motor no reconoce', detalle: null, tono: 'aviso' };
    default:
      // No se esconde: ocurrió algo y quedó registrado, aunque esta pantalla
      // todavía no sepa contarlo.
      return {
        texto: (ev?.tipo ?? 'Evento sin tipo').replaceAll('_', ' '),
        detalle: null,
        tono: 'neutro'
      };
  }
}

/** La línea completa de un evento, lista para dibujar. */
export function lineaDeActividad(ev) {
  return { ...loQuePaso(ev), quien: actorDe(ev), cuando: ev?.creado_en ?? null };
}
