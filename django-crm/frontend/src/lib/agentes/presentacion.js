/**
 * COMO SE PRESENTA UN AGENTE  --  13/11/2026
 *
 * La logica de la pantalla de Agentes, fuera de los .svelte para poder
 * probarla (el harness de vitest no compila .svelte). Tres reglas que la
 * pantalla anterior rompia y esta no:
 *
 *  1. UN NOMBRE PARA PERSONAS. La clave del rol ('soporte_tecnico_cliente') se
 *     mostraba capitalizada: "Soporte_tecnico_cliente". Ahora manda
 *     'nombre_visible'; sin el, la clave pasada a palabras.
 *
 *  2. EL FRENO QUE EXISTE, NO EL DECLARADO. La tarjeta decia "pide
 *     confirmacion antes" leyendo 'requiere_confirmacion', que el motor
 *     declara y NO aplica (motor.py). El freno real es 'aprobacion_humana'; y
 *     una que lo tiene puede hacerse sola en UN agente por autonomia ganada
 *     ('por_agente' de /reportes/autonomia-ganada). Si el dato no llego, se
 *     dice "sin dato" -- nunca se supone que va sola.
 *
 *  3. SIN DATO NO ES CERO. Un agente sin conversaciones no "escalo 0".
 */

/** Siglas que en un identificador van en mayusculas. */
const SIGLAS = new Set(['ont', 'onu', 'catv', 'tv', 'wifi', 'crm', 'sn', 'ssid', 'id', 'noc', 'ip', 'url', 'sla']);

/**
 * 'consultar_estado_ont' -> 'Consultar estado ONT'.
 * @param {string | null | undefined} id
 */
export function humanizar(id) {
  const palabras = String(id ?? '').split(/[_\s]+/).filter(Boolean)
    .map((p) => (SIGLAS.has(p.toLowerCase()) ? p.toUpperCase() : p.toLowerCase()));
  if (!palabras.length) return '';
  const primera = palabras[0];
  palabras[0] = SIGLAS.has(primera.toLowerCase()) ? primera : primera.charAt(0).toUpperCase() + primera.slice(1);
  return palabras.join(' ');
}

/** @param {any} agente */
export function nombreDe(agente) {
  return (agente?.nombre_visible || '').trim() || humanizar(agente?.nombre);
}

/** Cargo · area, o '' si no hay. @param {any} agente */
export function subtituloDe(agente) {
  return [agente?.cargo, agente?.area].filter(Boolean).join(' · ');
}

/**
 * Que hace, en una frase. NUNCA el primer parrafo del prompt: ese le habla al
 * modelo ("TODAVIA NO es cliente -- ..."), no a quien revisa. Sin resumen, lo
 * que atiende; sin eso, nada (la pantalla invita a completarlo).
 * El automatico (supervisor) si trae una descripcion escrita para personas.
 * @param {any} agente
 */
export function resumenDe(agente) {
  if (agente?.automatico) return (agente.descripcion || '').trim();
  const resumen = (agente?.resumen || '').trim();
  if (resumen) return resumen;
  const atiende = (agente?.atiende || '').trim();
  return atiende ? `Atiende: ${atiende}` : '';
}

/**
 * A quien le habla: 'cliente' (afuera, por WhatsApp), 'equipo' (uso interno)
 * o 'auto' (no conversa: revisa o propone).
 * @param {any} agente
 */
export function familia(agente) {
  if (agente?.automatico || agente?.operativo) return 'auto';
  return agente?.orientado_a === 'cliente_final' ? 'cliente' : 'equipo';
}

export const FAMILIAS = /** @type {const} */ ({
  cliente: { titulo: 'Atienden al cliente', nota: 'le hablan a alguien de afuera, por WhatsApp', habla: 'Cliente' },
  equipo: { titulo: 'Uso interno', nota: 'los usa el equipo desde el Asistente', habla: 'Equipo' },
  auto: { titulo: 'Automáticos y operativos', nota: 'no conversan: revisan o proponen, y una persona decide', habla: 'Nadie' }
});

/**
 * Indice de /reportes/autonomia-ganada por accion. null si no llego: no es
 * lo mismo que "ninguna accion pide aprobacion".
 * @param {any} autonomia
 * @returns {Record<string, any> | null}
 */
export function indiceDeAutonomia(autonomia) {
  if (!autonomia || !Array.isArray(autonomia.acciones)) return null;
  return Object.fromEntries(autonomia.acciones.map((/** @type {any} */ a) => [a.accion, a]));
}

/**
 * Como ejecuta ESTE agente una herramienta que escribe:
 *   'sola'        no pide aprobacion
 *   'ganada'      pedia, y este agente la gano (autonomia ganada)
 *   'degradada'   la habia ganado y la perdio sola (un efecto no se confirmo)
 *   'espera'      una persona la aprueba antes
 *   'sin_dato'    el motor no mando 'aprobacion_humana' (version vieja)
 * null para una consulta.
 *
 * @param {any} h herramienta de /agentes
 * @param {Record<string, any> | null} autonomiaDe indiceDeAutonomia(...)
 * @param {string} agente clave del rol
 */
export function modoDeAccion(h, autonomiaDe, agente) {
  if (h?.solo_lectura !== false) return null;
  if (typeof h.aprobacion_humana !== 'boolean') return 'sin_dato';
  if (!h.aprobacion_humana) return 'sola';
  const enEste = autonomiaDe?.[h.nombre]?.por_agente?.[agente];
  if (enEste?.autonoma) return 'ganada';
  if (enEste?.estado === 'degradada') return 'degradada';
  return 'espera';
}

export const MODOS = /** @type {const} */ ({
  sola: { texto: 'La hace sola', corto: 'Sola', tono: 'sola' },
  ganada: { texto: 'La hace sola (ganada)', corto: 'Sola', tono: 'sola' },
  degradada: { texto: 'Volvió a pedir aprobación', corto: 'Aprobación', tono: 'espera' },
  espera: { texto: 'Espera aprobación', corto: 'Aprobación', tono: 'espera' },
  sin_dato: { texto: 'Sin dato', corto: '?', tono: 'neutro' }
});

/** @param {string | null} modo */
export const vaSola = (modo) => modo === 'sola' || modo === 'ganada';

/**
 * Las herramientas por lo que HACEN: consulta, cuenta, actua. 'Actua' manda
 * sobre el tipo: una que escribe va ahi aunque ademas sea un agregado.
 * @param {any[]} herramientas
 */
export function porLoQueHace(herramientas) {
  /** @type {{consulta: any[], cuenta: any[], actua: any[]}} */
  const g = { consulta: [], cuenta: [], actua: [] };
  for (const h of herramientas ?? []) {
    if (h.solo_lectura === false) g.actua.push(h);
    else if (h.tipo === 'agregado') g.cuenta.push(h);
    else g.consulta.push(h);
  }
  return g;
}

/**
 * Cuantas acciones tiene un agente y como las ejecuta.
 * @param {any} agente @param {Record<string, any> | null} autonomiaDe
 */
export function conteoDeAcciones(agente, autonomiaDe) {
  const g = porLoQueHace(agente?.herramientas);
  let solas = 0, espera = 0, sinDato = 0;
  for (const h of g.actua) {
    const m = modoDeAccion(h, autonomiaDe, agente.nombre);
    if (vaSola(m)) solas++;
    else if (m === 'sin_dato') sinDato++;
    else espera++;
  }
  return { consultas: g.consulta.length, cuentas: g.cuenta.length, acciones: g.actua.length, solas, espera, sinDato };
}

/**
 * Los agentes en tres familias, en orden: los que le hablan al cliente
 * primero -- son los que pueden equivocarse delante de alguien de afuera.
 * Dentro de cada una, por nombre. Las familias vacias no salen.
 * @param {any[]} agentes
 */
export function agrupar(agentes) {
  /** @type {Record<string, any[]>} */
  const por = { cliente: [], equipo: [], auto: [] };
  for (const a of agentes ?? []) por[familia(a)].push(a);
  return /** @type {const} */ (['cliente', 'equipo', 'auto'])
    .filter((f) => por[f].length)
    .map((f) => ({
      clave: f, ...FAMILIAS[f],
      items: por[f].slice().sort((a, b) => nombreDe(a).localeCompare(nombreDe(b), 'es'))
    }));
}

/**
 * La franja de arriba: cuantos agentes, cuantos le hablan al cliente, y las
 * acciones que cambian algo, separadas en solas y con aprobacion.
 * @param {any[]} agentes conversacionales (los de /agentes)
 * @param {Record<string, any> | null} autonomiaDe
 */
export function resumenGlobal(agentes, autonomiaDe) {
  let cliente = 0, conAcciones = 0, acciones = 0, solas = 0, espera = 0, sinDato = 0;
  for (const a of agentes ?? []) {
    if (a.automatico) continue;
    if (a.orientado_a === 'cliente_final') cliente++;
    const c = conteoDeAcciones(a, autonomiaDe);
    if (c.acciones) conAcciones++;
    acciones += c.acciones; solas += c.solas; espera += c.espera; sinDato += c.sinDato;
  }
  return { cliente, conAcciones, acciones, solas, espera, sinDato };
}

/**
 * Quien puede que: una fila por herramienta que ESCRIBE, una columna por
 * agente que tiene alguna. Solo acciones: las consultas estan en la pagina de
 * cada agente, y meterlas aca esconderia lo que importa entre ochenta filas.
 * @param {any[]} agentes @param {Record<string, any> | null} autonomiaDe
 */
export function matriz(agentes, autonomiaDe) {
  const columnas = (agentes ?? []).filter((a) => !a.automatico && porLoQueHace(a.herramientas).actua.length);
  /** @type {Map<string, any>} */
  const filas = new Map();
  for (const a of columnas) {
    for (const h of porLoQueHace(a.herramientas).actua) {
      if (!filas.has(h.nombre)) filas.set(h.nombre, { nombre: h.nombre, resumen: h.resumen || '', celdas: {} });
      filas.get(h.nombre).celdas[a.nombre] = modoDeAccion(h, autonomiaDe, a.nombre);
    }
  }
  const sinAcciones = (agentes ?? []).filter((a) => !a.automatico && !columnas.includes(a));
  return {
    columnas,
    filas: [...filas.values()].sort((x, y) => humanizar(x.nombre).localeCompare(humanizar(y.nombre), 'es')),
    sinAcciones
  };
}

/** Caracteres de lo que recibe en cada turno. @param {any[]} piezas */
export function pesoDelPrompt(piezas) {
  return (piezas ?? []).reduce((n, p) => n + (p?.texto?.length ?? 0), 0);
}

/**
 * Lo que dice "Escalo" en la lista. Sin conversaciones en el periodo, un
 * guion: no hubo con que medir (no "0").
 * @param {any} d entrada de /reportes/agentes para este agente
 */
export function textoEscalo(d) {
  if (!d || !d.conversaciones) return '—';
  const pct = Math.round((d.escaladas / d.conversaciones) * 100);
  return `${d.escaladas} · ${pct} %`;
}

/** @param {number} n */
export const formatoNumero = (n) => Number(n ?? 0).toLocaleString('es-CO');

/** Una fila de bitacora, en palabras. @param {any} f */
export function textoDeBitacora(f) {
  const quien = f?.quien ? `: ${f.quien}` : '';
  const decidio = {
    solo: 'Lo hizo solo',
    aprobo: `Aprobó${quien}`,
    rechazo: `Rechazó${quien}`,
    espera: 'Espera aprobación'
  }[/** @type {string} */ (f?.decidio)] ?? '—';
  const resultado = {
    ok: 'Salió bien',
    fallo: `Falló${f?.error ? ` (${f.error})` : ''}`,
    no_se_ejecuto: 'No se ejecutó',
    pendiente: 'Pendiente'
  }[/** @type {string} */ (f?.resultado)] ?? '—';
  const tono = f?.resultado === 'ok' ? 'sola' : f?.resultado === 'fallo' ? 'critica' : 'neutro';
  return { decidio, resultado, tono };
}

/**
 * Fecha y hora en Bogota, corta: '13/11 10:42'. Las horas de la pantalla
 * siempre en Bogota, no en la zona del navegador.
 * @param {string} iso
 */
export function cuandoCorto(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const partes = new Intl.DateTimeFormat('es-CO', {
    timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
  }).formatToParts(d);
  const v = (/** @type {string} */ t) => partes.find((p) => p.type === t)?.value ?? '';
  return `${v('day')}/${v('month')} ${v('hour')}:${v('minute')}`;
}
