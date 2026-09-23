/**
 * Las derivaciones del panel «Detalle del hallazgo».
 *
 * Viven aquí, fuera del componente, por una razón práctica: son reglas de
 * presentación con casos borde —evidencia de un solo elemento, campos que no
 * coinciden, textos que cambian— y probarlas exige poder llamarlas. Dentro del
 * `.svelte` solo se podrían ejercitar montando el componente.
 *
 * NINGUNA INVENTA UN DATO. Todas leen lo que el backend ya manda, y cuando el
 * dato no está devuelven `null` para que el bloque que las usa no se dibuje.
 * Es la diferencia entre no mostrar algo y mostrarlo equivocado.
 */

/**
 * Lo que se repite idéntico en TODAS las observaciones: fuente, id y hora de
 * lectura. Cuando coinciden, la vista las muestra una sola vez.
 *
 * Con menos de dos observaciones no hay nada que agrupar.
 *
 * @param {any[] | null | undefined} evidencia
 * @returns {{fuente: string|null, id: string|null, leido: string|null} | null}
 */
export function comunDeEvidencia(evidencia) {
  if (!Array.isArray(evidencia) || evidencia.length < 2) return null;
  const unico = (/** @type {string} */ campo) => {
    const vals = new Set(evidencia.map((e) => e?.[campo]).filter(Boolean));
    return vals.size === 1 ? /** @type {string} */ ([...vals][0]) : null;
  };
  const fuente = unico('fuente');
  const id = unico('id');
  const leido = unico('observado_en');
  return fuente || id || leido ? { fuente, id, leido } : null;
}

/**
 * Las fuentes distintas que el análisis miró, tal como las nombra el backend.
 * No se traducen ni se agrupan: son las claves que el detector escribió.
 *
 * @param {any[] | null | undefined} evidencia
 */
export function fuentesDeEvidencia(evidencia) {
  if (!Array.isArray(evidencia)) return [];
  return [...new Set(evidencia.map((e) => e?.fuente).filter(Boolean))];
}

/**
 * De dónde sale el número de prioridad, si la evidencia lo dice.
 *
 * El backend manda una observación con fuente `calculo_prioridad`. Se trae
 * junto al número en lugar de dejarla a media pantalla de distancia: «30» solo
 * no dice nada, «30 · base 30» al menos dice de dónde viene.
 *
 * @param {any[] | null | undefined} evidencia
 */
export function baseDePrioridad(evidencia) {
  if (!Array.isArray(evidencia)) return null;
  const calc = evidencia.find((e) => String(e?.fuente ?? '').includes('prioridad'));
  return calc?.dato ?? null;
}

/**
 * El contraste CRM vs proveedor, SOLO si la evidencia lo trae.
 *
 * Se lee del texto de las observaciones porque el backend no lo manda como
 * campo aparte —y no se va a tocar el backend para esto—. Si ese texto cambia
 * y deja de coincidir, devuelve null y el bloque no se dibuja: prefiere no
 * mostrarse a afirmar algo que ya no es cierto.
 *
 * @param {any[] | null | undefined} evidencia
 * @returns {{crm: string, proveedor: string} | null}
 */
export function contrasteDeEstados(evidencia) {
  if (!Array.isArray(evidencia)) return null;
  const buscar = (/** @type {RegExp} */ re) => {
    const hit = evidencia.find((e) => re.test(String(e?.dato ?? '')));
    if (!hit) return null;
    const valor = String(hit.dato).split(':').slice(1).join(':').trim();
    return valor || null;
  };
  const crm = buscar(/^estado actual\s*:/i);
  const proveedor = buscar(/^estado en el proveedor\s*:/i);
  return crm && proveedor ? { crm, proveedor } : null;
}

/**
 * «hace 3 h» dice lo que una fecha absoluta obliga a calcular. Importa porque
 * `observado_en` existe justamente para saber si la propuesta se tomó con
 * información fresca o vieja.
 *
 * @param {string | null | undefined} iso
 * @param {number} [ahora]  para poder probarlo sin depender del reloj
 */
export function haceCuanto(iso, ahora = Date.now()) {
  if (!iso) return '—';
  const ms = ahora - new Date(iso).getTime();
  if (Number.isNaN(ms)) return '—';
  // Una fecha futura no se dice como "hace -5 min".
  if (ms < 0) return 'recién';
  const min = Math.round(ms / 60000);
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 48) return `hace ${h} h`;
  return `hace ${Math.round(h / 24)} días`;
}

/**
 * De la expiración importa cuánto queda, no la fecha.
 *
 * @param {string | null | undefined} iso
 * @param {number} [ahora]
 */
export function expiraEn(iso, ahora = Date.now()) {
  if (!iso) return '—';
  const ms = new Date(iso).getTime() - ahora;
  if (Number.isNaN(ms)) return '—';
  if (ms <= 0) return 'vencida';
  const h = Math.round(ms / 3600000);
  return h < 48 ? `en ${h} h` : `en ${Math.round(h / 24)} días`;
}
