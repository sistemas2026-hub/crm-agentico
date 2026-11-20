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
 * Cómo llegó la tarea a su estado, en una línea (12/11/2026).
 *
 * Desde ese día lo no crítico NACE delegado (PRD §2): «delegada» ya no
 * significa que alguien la encendió. Decir «Delegada por una persona» de una
 * que trae el defecto le atribuiría a alguien algo que nadie hizo.
 *
 * @param {{ delegada: boolean, por_omision?: boolean, delegada_por?: string,
 *           quitada_por?: string }} t
 * @returns {string}
 */
export function comoLlego(t) {
  if (t.delegada && t.por_omision) return 'La hace sola desde el primer día: nadie la cambió.';
  if (t.delegada) return `La delegó ${t.delegada_por || 'una persona'}`;
  if (t.quitada_por) return `La quitó ${t.quitada_por}`;
  return 'Sin delegar.';
}

/**
 * Las tareas en dos grupos: lo que hace solo y lo que espera a una persona
 * por ser crítico. `critica` lo decide el backend (el catálogo); un dato que
 * falta cuenta como crítico, igual que allá.
 *
 * @template {{ critica?: boolean }} T
 * @param {T[]} tareas
 * @returns {{ solas: T[], criticas: T[] }}
 */
export function separarPorCritica(tareas) {
  const solas = [];
  const criticas = [];
  for (const t of tareas ?? []) (t.critica === false ? solas : criticas).push(t);
  return { solas, criticas };
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
