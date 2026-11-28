/**
 * EL PULSO DEL NOC  --  21/11/2026.
 *
 * Una franja igual en las siete subpantallas del Supervisor NOC (rediseño
 * aprobado el 21/11/2026): seis cifras que dicen si hay que ir a algún lado
 * sin abrir cada pantalla, y cada una lleva a la suya.
 *
 *   SLA vencido      → Pendientes      (propuestas con plazo vencido / por vencer)
 *   Caídas de PON    → Fallas de red   (caídas vivas)
 *   Reportando       → Programación    (cuadrillas del día con posición)
 *   Sin repartir     → Despacho        (órdenes que esperan cuadrilla)
 *   Kits incompletos → Programación    (cuadrillas con faltantes)
 *   Supervisor       → Ajustes         (si el freno de mano está puesto)
 *
 * NADA SE INVENTA. Una fuente que no respondió da `valor: null` y la ficha
 * dice «sin dato», nunca 0: «0 caídas» afirmaría que la red está bien cuando
 * lo cierto es que no se pudo preguntar (misma regla que la franja de
 * Programación y que «Ahora mismo» en Pendientes).
 *
 * Lógica pura: recibe lo que ya devuelven los lectores del servidor.
 */

/** Los estados de una caída que cuentan como viva (operaciones/aviso_de_caida.py, VIVOS). */
const CAIDA_VIVA = new Set(['detectada', 'investigando', 'confirmada', 'en_atencion']);

/** Las propuestas que el Supervisor cierra solo no cuentan para el SLA de una persona. */
const NO_CUENTA_PARA_SLA = new Set(['caso_desincronizado']);

/**
 * @typedef {{ clave: string, valor: string | null, texto: string, tono: 'critico'|'alerta'|'ok'|'accion'|'neutro', href: string, motivo?: string }} Ficha
 */

/**
 * @param {any[] | null} propuestas  pendientes (estado 'propuesta'), o null si no se pudieron leer
 * @returns {Ficha}
 */
export function fichaDeSla(propuestas) {
  const href = '/supervisor-noc';
  if (!Array.isArray(propuestas)) return { clave: 'sla', valor: null, texto: 'SLA · sin dato', tono: 'neutro', href };
  let vencidas = 0;
  let pronto = 0;
  for (const p of propuestas) {
    if (NO_CUENTA_PARA_SLA.has(p?.tipo_senal)) continue;
    if (p?.sla_estado === 'VENCIDA') vencidas += 1;
    else if (p?.sla_estado === 'VENCE_PRONTO') pronto += 1;
  }
  return {
    clave: 'sla',
    valor: String(vencidas),
    texto: `SLA vencido · ${pronto} por vencer`,
    tono: vencidas ? 'critico' : pronto ? 'alerta' : 'ok',
    href
  };
}

/**
 * @param {any[] | null} fallas  lo que devuelve GET /operaciones/fallas-de-red/ (`fallas`)
 * @returns {Ficha}
 */
export function fichaDeCaidas(fallas) {
  const href = '/supervisor-noc/fallas';
  if (!Array.isArray(fallas)) return { clave: 'caidas', valor: null, texto: 'Caídas de PON · sin dato', tono: 'neutro', href };
  const vivas = fallas.filter((f) => CAIDA_VIVA.has(String(f?.estado ?? ''))).length;
  return {
    clave: 'caidas',
    valor: String(vivas),
    texto: vivas === 1 ? 'Caída de PON activa' : 'Caídas de PON activas',
    tono: vivas ? 'critico' : 'ok',
    href
  };
}

/**
 * @param {any | null} publicado  lo que devuelve GET /campo/dia-publicado/
 * @returns {Ficha}
 */
export function fichaDeReportando(publicado) {
  const href = '/supervisor-noc/programacion';
  const cuadrillas = publicado?.cuadrillas;
  if (!Array.isArray(cuadrillas)) return { clave: 'reportando', valor: null, texto: 'Cuadrillas · sin dato', tono: 'neutro', href };
  const total = cuadrillas.length;
  const con = cuadrillas.filter((c) => c?.posicion).length;
  return {
    clave: 'reportando',
    valor: total ? `${con}/${total}` : '0',
    texto: total ? 'Cuadrillas reportando' : 'Sin cuadrillas armadas hoy',
    tono: !total ? 'neutro' : con === total ? 'ok' : 'alerta',
    href
  };
}

/**
 * @param {any | null} publicado
 * @returns {Ficha}
 */
export function fichaDeSinRepartir(publicado) {
  const href = '/supervisor-noc/despacho';
  const n = publicado?.cuentas?.esperan;
  if (typeof n !== 'number') return { clave: 'sin_repartir', valor: null, texto: 'Sin repartir · sin dato', tono: 'neutro', href };
  return {
    clave: 'sin_repartir',
    valor: String(n),
    texto: n === 1 ? 'Orden sin repartir' : 'Órdenes sin repartir',
    tono: n ? 'alerta' : 'ok',
    href
  };
}

/**
 * @param {any | null} material  lo que devuelve el lector del material del día
 * @returns {Ficha}
 */
export function fichaDeKits(material) {
  const href = '/supervisor-noc/programacion';
  const n = material?.cuentas?.con_faltantes;
  if (typeof n !== 'number') return { clave: 'kits', valor: null, texto: 'Kits · sin dato', tono: 'neutro', href };
  return {
    clave: 'kits',
    valor: String(n),
    texto: n === 1 ? 'Kit incompleto' : 'Kits incompletos',
    tono: n ? 'critico' : 'ok',
    href
  };
}

/**
 * El Supervisor: si puede actuar o si el freno de mano está puesto.
 *
 * `permitido` lo decide el motor (`/autonomia`): `false` es «no actúa» —por el
 * freno o por el nivel—, y el motivo viaja en el título de la ficha.
 *
 * @param {{ permitido?: boolean | null, motivo?: string, estado?: any } | null} autonomia
 * @returns {Ficha & { motivo?: string }}
 */
export function fichaDelSupervisor(autonomia) {
  const href = '/supervisor-noc/ajustes';
  const permitido = autonomia?.permitido;
  if (permitido !== true && permitido !== false) {
    return { clave: 'supervisor', valor: null, texto: 'Supervisor · sin dato', tono: 'neutro', href };
  }
  return {
    clave: 'supervisor',
    valor: permitido ? 'Actúa' : 'Frenado',
    texto: permitido ? 'Supervisor · freno libre' : 'Supervisor · no actúa',
    tono: permitido ? 'accion' : 'critico',
    href,
    motivo: permitido ? '' : String(autonomia?.motivo || 'El freno de mano está puesto.')
  };
}

/**
 * Las seis fichas, en el orden en que se dibujan.
 *
 * @param {{ propuestas?: any[] | null, fallas?: any[] | null, publicado?: any, material?: any, autonomia?: any }} fuentes
 * @returns {Ficha[]}
 */
export function armarPulso(fuentes) {
  return [
    fichaDeSla(fuentes?.propuestas ?? null),
    fichaDeCaidas(fuentes?.fallas ?? null),
    fichaDeReportando(fuentes?.publicado ?? null),
    fichaDeSinRepartir(fuentes?.publicado ?? null),
    fichaDeKits(fuentes?.material ?? null),
    fichaDelSupervisor(fuentes?.autonomia ?? null)
  ];
}

/**
 * Qué ficha corresponde a la pantalla abierta, para marcarla.
 * Pendientes es la ruta exacta; las demás, por prefijo.
 *
 * @param {Ficha[]} fichas
 * @param {string} ruta  $page.url.pathname
 * @returns {string | null}  la `clave` activa
 */
export function fichaActiva(fichas, ruta) {
  const r = String(ruta ?? '').replace(/\/+$/, '') || '/';
  if (r === '/supervisor-noc') return 'sla';
  if (r.startsWith('/supervisor-noc/planes-semanales')) return 'reportando';
  const f = (fichas ?? []).find((x) => x.href !== '/supervisor-noc' && r.startsWith(x.href));
  return f ? f.clave : null;
}
