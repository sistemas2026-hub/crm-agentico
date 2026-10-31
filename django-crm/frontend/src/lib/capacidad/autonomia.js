/**
 * La autonomía ganada, dicha para quien decide (31/10/2026, PRD §2, Ola 3).
 *
 * El motor manda códigos y números (`nucleo/seguridad/autonomia_ganada.py`);
 * acá se arman las frases. Un código que no está en la lista se muestra tal
 * cual: esconderlo dejaría a la persona sin saber qué falta.
 */

/** Por qué una acción no es candidata (condiciones 1 y 2 del PRD §2). */
export const NO_CANDIDATA = /** @type {Record<string, string>} */ ({
  efecto_no_verificable: 'su efecto no se puede comprobar en código',
  sin_previas_en_codigo: 'no tiene condiciones previas que se comprueben en código'
});

/**
 * Qué le falta a una candidata para ser elegible (condición 3).
 * @param {{ condicion: string, tiene: number | null, necesita: number }} f
 */
export function textoDeFalta(f) {
  const pct = (/** @type {number | null} */ x) =>
    x === null || x === undefined ? '—' : `${Math.round(x * 1000) / 10}%`;
  switch (f.condicion) {
    case 'minimo_revisadas':
      return `Revisadas por una persona: ${f.tiene} de ${f.necesita}.`;
    case 'tasa_minima_aprobacion':
      return f.tiene === null
        ? `Ninguna revisada todavía: hace falta al menos ${pct(f.necesita)} aprobadas.`
        : `Aprobadas sin cambios: ${pct(f.tiene)}; hace falta ${pct(f.necesita)}.`;
    case 'cero_no_confirmadas':
      return `${f.tiene} ${f.tiene === 1 ? 'vez' : 'veces'} el efecto no se confirmó después de ejecutarla: tiene que ser cero.`;
    case 'cero_fallidas':
      return `${f.tiene} ${f.tiene === 1 ? 'ejecución falló' : 'ejecuciones fallaron'} o quedaron inciertas: tiene que ser cero.`;
    default:
      return `${f.condicion}: ${f.tiene} (hace falta ${f.necesita}).`;
  }
}

/** @param {string[] | null | undefined} codigos */
export function textoDeNoCandidata(codigos) {
  return (codigos ?? []).map((c) => NO_CANDIDATA[c] ?? c).join('; ');
}
