/**
 * QUÉ SE LE DICE A LA PERSONA DESPUÉS DE CADA ACCIÓN DE PLANES SEMANALES
 * 21/11/2026.
 *
 * La pantalla solo distinguía «secuenciar»: después de programar,
 * reprogramar, cambiar una secuencia o analizar decía «Plan publicado. No se
 * ejecutó ninguna programación.», que era falso en los cuatro casos. Cada
 * acción de `planes-semanales/+page.server.js` devuelve su `tipo`; acá se
 * traduce, y un tipo desconocido no inventa nada.
 *
 * @param {{ tipo?: string, orden?: string|number, secuencia?: string|number,
 *           asistente?: { recomendaciones?: unknown[] } } | null | undefined} form
 * @returns {string}
 */
export function avisoDelPlan(form) {
  switch (form?.tipo) {
    case 'secuenciar':
      return 'Orden propuesto actualizado. No se reprogramó ninguna orden ni se cambió ninguna asignación.';
    case 'publicar':
      return 'Plan publicado. No se ejecutó ninguna programación.';
    case 'programar':
      return `Orden #${form.orden} programada en el plan.`;
    case 'reprogramar':
      return `Orden #${form.orden} reprogramada. Quedó registrada como novedad operativa.`;
    case 'secuencia':
      return Number(form.secuencia) === 0
        ? 'La línea quedó sin secuenciar. La orden sigue el mismo día.'
        : `La línea quedó en la secuencia ${form.secuencia}. La orden sigue el mismo día.`;
    case 'analizar': {
      const n = Array.isArray(form.asistente?.recomendaciones) ? form.asistente.recomendaciones.length : 0;
      return n === 0
        ? 'Análisis listo: el asistente no encontró nada nuevo. No programó ni asignó nada.'
        : `Análisis listo: ${n} ${n === 1 ? 'recomendación' : 'recomendaciones'}. No programó ni asignó nada.`;
    }
    default:
      return 'Hecho.';
  }
}
