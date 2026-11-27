/**
 * El ancho de banda de cada plan en la red (27/11/2026): lo que se muestra en
 * la tabla de Programación y lo que se guarda de ella. Puro, sin red ni
 * entorno: la lectura del motor está en $lib/server/v2/perfiles-de-velocidad.js.
 */

/**
 * @typedef {{ nombre: string, kbps: number | null }} Perfil
 * @typedef {{ nombre: string, bajada: string, subida: string,
 *             sugerido: { bajada: string, subida: string } }} PlanDelMotor
 * @typedef {{ disponible: boolean, error: string,
 *             perfiles: { bajada: Perfil[], subida: Perfil[] }, planes: PlanDelMotor[] }} Perfiles
 * @typedef {{ plan: string, bajada: string, subida: string }} Guardado
 * @typedef {{ plan: string, velocidad: string, bajada: string, subida: string,
 *             sugerido: boolean, seVende: boolean }} Fila
 */

/** @param {unknown} t */
const llano = (t) => String(t ?? '').split(/\s+/).filter(Boolean).join(' ').toLowerCase();

/**
 * Las filas de la tabla, como se muestran: cada plan que se vende, con lo
 * guardado o, si ese plan no tiene nada guardado, lo sugerido (y marcado como
 * sugerido). Un plan guardado que ya no se vende también sale, al final: si no
 * saliera, el próximo guardado lo borraría sin que nadie lo viera.
 * @param {Perfiles | null} perfiles @param {Guardado[] | null | undefined} guardados
 * @returns {Fila[]}
 */
export function filasDePerfiles(perfiles, guardados) {
  const porPlan = new Map((guardados ?? []).map((g) => [llano(g.plan), g]));
  /** @type {Fila[]} */
  const filas = [];
  const vistos = new Set();
  for (const p of perfiles?.planes ?? []) {
    const g = porPlan.get(llano(p.nombre));
    vistos.add(llano(p.nombre));
    filas.push({
      plan: p.nombre,
      velocidad: p.bajada || p.subida ? `${p.bajada || '?'} / ${p.subida || '?'}` : '',
      bajada: g ? g.bajada : p.sugerido?.bajada ?? '',
      subida: g ? g.subida : p.sugerido?.subida ?? '',
      sugerido: !g && !!(p.sugerido?.bajada || p.sugerido?.subida),
      seVende: true
    });
  }
  for (const g of guardados ?? []) {
    if (vistos.has(llano(g.plan))) continue;
    filas.push({ plan: g.plan, velocidad: '', bajada: g.bajada, subida: g.subida, sugerido: false, seVende: false });
  }
  return filas;
}

/**
 * Del formulario a la tabla que se guarda. `undefined` si la tabla NO estaba
 * en pantalla (el motor no contestó): así el guardado no la toca.
 *
 * Una fila sin ningún perfil viaja igual: el backend la descarta, y con la
 * tabla cargada ese plan no se activa (lo dice al pedir).
 * @param {FormData} f
 * @returns {Guardado[] | undefined}
 */
export function perfilesDelFormulario(f) {
  if (f.get('perfiles_en_el_formulario') !== '1') return undefined;
  /** @type {Guardado[]} */
  const filas = [];
  for (const k of new Set(f.keys())) {
    const m = /^perfil_plan_(\d+)$/.exec(k);
    if (!m) continue;
    filas.push({
      plan: String(f.get(k) ?? '').trim(),
      bajada: String(f.get(`perfil_bajada_${m[1]}`) ?? '').trim(),
      subida: String(f.get(`perfil_subida_${m[1]}`) ?? '').trim()
    });
  }
  return filas;
}
