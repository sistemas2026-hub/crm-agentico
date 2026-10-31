/**
 * Lo que Despacho propone al tocar «Despachar»  --  19/10/2026
 *
 * Pedido por el usuario: que la plantilla, la fecha y la prioridad vengan
 * elegidas según lo que vio el Supervisor. Son PROPUESTAS: quien despacha las
 * ve y las cambia. La plantilla y la prioridad las elige el backend
 * (`plantilla_sugerida` y `prioridad_sugerida` en la ficha; la prioridad, desde
 * el 23/10/2026, con la misma regla que usa el Supervisor al crear la orden);
 * acá vive la fecha, que depende de la plantilla que se elija en pantalla.
 */
/** @param {Date} d */
const ymd = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/**
 * «Para cuándo»: el día en que se creó el ticket más el plazo de la
 * plantilla. Si ese día ya pasó, hoy -- lo vencido se hace cuanto antes, no
 * en una fecha del pasado que el formulario aceptaría igual.
 *
 * Se cuenta en DÍAS DE CALENDARIO y con la fecha local de quien despacha: es
 * lo que muestra el campo de fecha.
 *
 * Vacío si falta la creación o la plantilla no declara plazo: sin esos dos
 * datos no hay de dónde sacar una fecha, y una inventada parece decidida.
 *
 * @param {string | null | undefined} creadoISO  cuándo se creó el ticket
 * @param {number | null | undefined} plazoDias  el plazo de la plantilla
 * @param {Date} [hoy]
 * @returns {string} 'AAAA-MM-DD' o ''
 */
export function fechaSugerida(creadoISO, plazoDias, hoy = new Date()) {
  if (!creadoISO || typeof plazoDias !== 'number' || plazoDias < 0) return '';
  const creado = new Date(creadoISO);
  if (Number.isNaN(creado.getTime())) return '';
  const limite = new Date(creado.getFullYear(), creado.getMonth(), creado.getDate() + plazoDias);
  const hoyLocal = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return ymd(limite < hoyLocal ? hoyLocal : limite);
}
