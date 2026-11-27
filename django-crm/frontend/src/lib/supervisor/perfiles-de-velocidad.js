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
 *             sugerido: boolean, seVende: boolean,
 *             sugeridos: { bajada: string, subida: string },
 *             kbps: { bajada: number | null, subida: number | null } }} Fila
 */

/**
 * «700M» -> 700000, «215040k» -> 215040, «1G» -> 1000000 (kbps, unidades de
 * red). `null` si no se entiende: un número sin unidad no dice si son bits o
 * kilobits. La misma regla que el motor (`activar_onu.velocidad_kbps`).
 * @param {unknown} texto @returns {number | null}
 */
export function velocidadKbps(texto) {
  const m = /^\s*(\d+(?:[.,]\d+)?)\s*([kmg])\s*$/i.exec(String(texto ?? ''));
  if (!m) return null;
  const factor = /** @type {Record<string, number>} */ ({ k: 1, m: 1000, g: 1000000 })[m[2].toLowerCase()];
  return Math.round(Number(m[1].replace(',', '.')) * factor);
}

/**
 * Cómo se lee un perfil en la lista (27/11/2026): el nombre y su velocidad, y
 * si es el sugerido para ese plan. «PLAN_100MB» y «PLAN_1000MB» se confundían
 * a simple vista: con la velocidad al lado no.
 * @param {Perfil} p @param {string} [sugerido]
 */
export function etiquetaDePerfil(p, sugerido = '') {
  const velocidad = p.kbps === 0 ? 'sin límite'
    : typeof p.kbps === 'number' ? `${Math.round(p.kbps / 1000)} megas` : '';
  return [p.nombre, velocidad].filter(Boolean).join(' — ') + (sugerido && p.nombre === sugerido ? ' · sugerido' : '');
}

/**
 * Si el perfil elegido queda POR DEBAJO de lo que paga el cliente (27/11/2026).
 * `null` si no se puede saber (sin perfil, sin velocidad del plan, o un perfil
 * «sin límite»).
 * @param {string} elegido @param {Perfil[]} perfiles @param {number | null} kbpsDelPlan
 */
export function quedaPorDebajo(elegido, perfiles, kbpsDelPlan) {
  if (!elegido || !kbpsDelPlan) return null;
  const p = perfiles.find((x) => x.nombre === elegido);
  if (!p || typeof p.kbps !== 'number' || p.kbps === 0) return null;
  return p.kbps < kbpsDelPlan;
}

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
      seVende: true,
      sugeridos: { bajada: p.sugerido?.bajada ?? '', subida: p.sugerido?.subida ?? '' },
      kbps: { bajada: velocidadKbps(p.bajada), subida: velocidadKbps(p.subida) }
    });
  }
  for (const g of guardados ?? []) {
    if (vistos.has(llano(g.plan))) continue;
    filas.push({ plan: g.plan, velocidad: '', bajada: g.bajada, subida: g.subida, sugerido: false, seVende: false,
                 sugeridos: { bajada: '', subida: '' }, kbps: { bajada: null, subida: null } });
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
