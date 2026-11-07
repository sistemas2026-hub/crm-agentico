/**
 * Cómo se dice el estado de una tarea en «Ajustes del Supervisor» (27/10/2026).
 *
 * Fuera del componente para poder probarlo: «delegada» y «delegada y
 * andando» no son lo mismo, y una pantalla que las confunde miente sin verse
 * rota. El 15/10 una tarea estuvo delegada, con el nivel en 3, y nada la
 * corrió en cinco vueltas porque faltaba el ciclo horario.
 *
 * El backend calcula las precondiciones (`nivel_alcanza`,
 * `la_despierta_algo`, `requiere`); acá solo se ponen en palabras.
 */

/**
 * @typedef {{ delegada: boolean, exige_nivel: number, nivel_alcanza: boolean,
 *             la_despierta_algo?: { si: boolean, por_que?: string } | null,
 *             requiere?: { nombre: string, delegada: boolean }[] }} Tarea
 */

/**
 * Lo que le falta a una tarea para actuar sola. Vacío = no le falta nada.
 *
 * Se dice también de una tarea SIN delegar: es lo que la persona necesita
 * saber antes del clic, no después.
 *
 * @param {Tarea} t
 * @param {number} nivelEfectivo
 * @returns {string[]}
 */
export function loQueLeFalta(t, nivelEfectivo) {
  /** @type {string[]} */
  const faltan = [];
  if (!t.nivel_alcanza) {
    faltan.push(
      `Necesita nivel ${t.exige_nivel} de autonomía y el que aplica hoy es ${nivelEfectivo}.`
    );
  }
  if (t.la_despierta_algo && !t.la_despierta_algo.si && t.la_despierta_algo.por_que) {
    const p = t.la_despierta_algo.por_que;
    faltan.push(p.charAt(0).toUpperCase() + p.slice(1) + '.');
  }
  for (const r of t.requiere ?? []) {
    if (!r.delegada) faltan.push(`Necesita también «${r.nombre}», que no está delegada.`);
  }
  return faltan;
}

/**
 * El punto de color de la fila: apagada, andando, o delegada sin poder actuar.
 *
 * @param {Tarea} t
 * @param {number} nivelEfectivo
 * @returns {'apagada' | 'andando' | 'trabada'}
 */
export function tonoDeLaTarea(t, nivelEfectivo) {
  if (!t.delegada) return 'apagada';
  return loQueLeFalta(t, nivelEfectivo).length ? 'trabada' : 'andando';
}
