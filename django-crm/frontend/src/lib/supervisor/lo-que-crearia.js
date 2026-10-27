/**
 * Los totales de «Lo que crearía el Supervisor» (27/10/2026). Pedido del
 * usuario: verificar desde la pantalla lo que hasta ahora daba el comando
 * `informe_de_despacho` — cuántas órdenes eligen la plantilla por el asunto
 * o por la labor, cuántas tienen nivel y cuántas tienen el equipo caído —,
 * sin contar filas a mano. Fuera del componente para poder probarlo.
 */

/** El orden de fábrica de los niveles (`campo/niveles.py`). */
const ORDEN_DE_LOS_NIVELES = ['urgente', 'normal', 'programable'];

/**
 * @param {Array<{ por?: string, nivel?: string, nivel_nombre?: string,
 *                 equipo_caido?: boolean }>} crear
 */
export function totalesDeLoQueCrearia(crear) {
  const filas = Array.isArray(crear) ? crear : [];
  /** @type {Record<string, { nombre: string, n: number }>} */
  const porNivel = {};
  const t = { porAsunto: 0, porLabor: 0, conNivel: 0, sinNivel: 0, equipoCaido: 0, porNivel };
  for (const f of filas) {
    if (f?.por === 'asunto') t.porAsunto += 1;
    else t.porLabor += 1;
    if (f?.nivel) {
      t.conNivel += 1;
      porNivel[f.nivel] ??= { nombre: f.nivel_nombre || f.nivel, n: 0 };
      porNivel[f.nivel].n += 1;
    } else {
      t.sinNivel += 1;
    }
    if (f?.equipo_caido) t.equipoCaido += 1;
  }
  return t;
}

/**
 * Las líneas que van arriba de la tabla.
 *
 * @param {ReturnType<typeof totalesDeLoQueCrearia>} t
 */
export function textoDeLosTotales(t) {
  const plantilla = `Plantilla por el asunto ${t.porAsunto} · por la labor ${t.porLabor}`;
  const codigos = Object.keys(t.porNivel).sort((a, b) => {
    const i = ORDEN_DE_LOS_NIVELES.indexOf(a);
    const j = ORDEN_DE_LOS_NIVELES.indexOf(b);
    return (i < 0 ? 99 : i) - (j < 0 ? 99 : j);
  });
  const niveles = codigos.map((c) => `${t.porNivel[c].nombre} ${t.porNivel[c].n}`);
  const nivel = t.conNivel
    ? `Con nivel ${t.conNivel} (${niveles.join(', ')}) · sin nivel ${t.sinNivel}`
    : 'Ningún asunto tiene nivel todavía: la prioridad sale del plazo de la plantilla';
  const caido = t.equipoCaido ? ` · equipo caído ${t.equipoCaido}` : '';
  return [plantilla, nivel + caido];
}
