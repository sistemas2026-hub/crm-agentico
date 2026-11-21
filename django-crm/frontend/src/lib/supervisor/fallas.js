/**
 * «Fallas de red»: cómo se dice cada cosa (30/10/2026, PRD §8.17, Ola 2).
 *
 * El backend contesta códigos fijos (`operaciones/aviso_de_caida.py`) y el
 * motor los motivos de cada aviso que no salió
 * (`nucleo/seguimiento/mensajes_automaticos.py`). Acá se traducen para quien
 * aprueba. Un código que no está en la lista se muestra tal cual: esconderlo
 * dejaría a la persona sin saber qué pasó.
 */

/** Por qué una caída no se puede avisar. */
export const POR_QUE_NO = /** @type {Record<string, string>} */ ({
  corte_de_energia: 'Es un corte de energía, no una falla de la red: no se avisa.',
  alerta_sin_aviso: 'SmartOLT no dice que sea una falla de fibra: no se avisa.',
  ya_no_esta_activa: 'La caída ya no está activa.',
  sin_puerto: 'No se pudo leer el puerto de la caída.',
  no_es_de_pon: 'No es una caída de un puerto PON.'
});

/** Por qué no se pudo preparar o aprobar. */
export const ERRORES = /** @type {Record<string, string>} */ ({
  YA_APROBADO: 'Ya se aprobó el aviso de esta caída.',
  CARGANDO:
    'Dexter está armando la lista de clientes del ISP (la primera vez tarda cerca de un minuto). Probá de nuevo en un momento.',
  SIN_CLIENTES: 'Ningún cliente activo se cayó junto en este puerto: no hay a quién avisar.',
  NO_CONFIGURADO: 'El aviso de caídas no está configurado para esta empresa.',
  MOTOR_NO_CONTESTA: 'Dexter no respondió. Probá de nuevo.',
  OPTICO_NO_CONTESTA: 'SmartOLT no respondió. Probá de nuevo.',
  FALTA_QUIEN_APRUEBA: 'No se pudo saber quién aprueba. Volvé a iniciar sesión.',
  NO_EXISTE: 'Esa caída ya no existe.',
  ...POR_QUE_NO
});

/** Por qué un aviso no está listo para salir (motor: mensajes_automaticos.listo). */
export const NO_LISTO = /** @type {Record<string, string>} */ ({
  apagado: 'El aviso «Falla en la red» está apagado en Mensajes automáticos.',
  plantilla_desactivada: 'La plantilla del aviso está desactivada.',
  canal_apagado: 'WhatsApp no está conectado para esta empresa.',
  meta_no_contesta: 'Meta no respondió al revisar la plantilla.',
  plantilla_no_aprobada: 'La plantilla del aviso todavía no está aprobada por Meta.',
  plantilla_no_coincide: 'La plantilla aprobada no coincide con los datos elegidos.',
  sin_indicativo: 'Falta el indicativo del país de la empresa: sin él no se le puede escribir a ningún celular del ISP.'
});

/** Por qué un aviso a un cliente no salió. */
export const MOTIVOS = /** @type {Record<string, string>} */ ({
  de_baja: 'pidieron no recibir mensajes',
  sin_movil: 'sin celular en el ISP',
  sin_indicativo: 'falta el indicativo del país',
  fuera_de_prueba: 'fuera de los números de prueba',
  ya_enviado: 'ya avisados',
  isp_no_contesta: 'el ISP no respondió',
  rechazado: 'Meta los rechazó',
  incierto: 'no se pudo confirmar',
  ...Object.fromEntries(Object.entries(NO_LISTO).map(([k, v]) => [k, v.toLowerCase()]))
});

/** Por qué se detuvo un envío ya aprobado (backend: AvisoDeCaida.motivo_detencion). */
export const DETENCION = /** @type {Record<string, string>} */ ({
  SITUACION_RESUELTA: 'La caída se resolvió antes de terminar: no se le escribe a nadie más.',
  TOPE_DE_VUELTAS: 'Se agotaron los reintentos; los que faltaban no recibieron el aviso.',
  VOLVIO_A_CAER: 'La falla volvió antes de avisar que estaba resuelta: no se le dijo a nadie que volvió.'
});

/**
 * Por qué se detuvo un envío, dicho para una persona.
 * @param {string | null | undefined} codigo
 */
export function textoDeDetencion(codigo) {
  const c = String(codigo ?? '');
  if (!c) return '';
  if (DETENCION[c]) return DETENCION[c];
  if (c.startsWith('AVISO_')) {
    const motivo = c.slice('AVISO_'.length).toLowerCase();
    if (NO_LISTO[motivo]) return `${NO_LISTO[motivo]} Los que faltaban no recibieron el aviso.`;
  }
  return c;
}

/** @param {string | null | undefined} codigo */
export function textoDelError(codigo) {
  const c = String(codigo ?? '');
  if (ERRORES[c]) return ERRORES[c];
  if (c.startsWith('AVISO_')) {
    const motivo = c.slice('AVISO_'.length).toLowerCase();
    if (NO_LISTO[motivo]) return `${NO_LISTO[motivo]} Encendelo antes de aprobar.`;
  }
  return c || 'No se pudo completar la operación.';
}

/**
 * Los motivos de lo que no salió, de mayor a menor.
 * @param {Record<string, number> | null | undefined} motivos
 * @returns {string[]}
 */
export function motivosLegibles(motivos) {
  return Object.entries(motivos ?? {})
    .filter(([, n]) => Number(n) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([k, n]) => `${n} ${MOTIVOS[k] ?? k}`);
}

/**
 * Cuánto avanzó el envío, de 0 a 100: lo que ya se resolvió (enviado,
 * descartado o con motivo) sobre el total aprobado.
 * @param {{clientes?: number, pendientes?: number} | null | undefined} aviso
 */
export function avance(aviso) {
  const total = Number(aviso?.clientes ?? 0);
  if (!total) return 0;
  const hecho = total - Number(aviso?.pendientes ?? 0);
  return Math.max(0, Math.min(100, Math.round((hecho / total) * 100)));
}

/* ===========================================================================
   EL REDISEÑO DEL 21/11/2026: estado, grupo y resumen de cada caída.
   El backend ya mandaba `estado`, `riesgo` y `tipo_alerta` y la pantalla no
   los usaba: todas las caídas llevaban el mismo punto rojo, fuera una viva,
   una de energía o una que terminó hace horas.
   =========================================================================== */

/** Los estados de una situación que todavía es una caída viva (aviso_de_caida.VIVOS). */
export const VIVOS = new Set(['detectada', 'investigando', 'confirmada', 'en_atencion']);

const ESTADO_LEGIBLE = /** @type {Record<string, string>} */ ({
  detectada: 'Detectada',
  investigando: 'Investigando',
  confirmada: 'Confirmada',
  en_atencion: 'En atención',
  en_verificacion: 'En verificación',
  resuelta: 'Restablecida',
  cerrada: 'Cerrada',
  descartada: 'Descartada'
});

/** Qué tipo de caída según SmartOLT. */
export const TIPO_ALERTA = /** @type {Record<string, string>} */ ({
  los: 'LOS · fibra',
  partial_los: 'LOS parcial',
  power: 'Energía'
});

/**
 * En qué grupo va una caída y cómo se rotula.
 *   activa    — viva y sin aviso en curso
 *   avisando  — con aviso enviándose
 *   resuelta  — ya no está viva (se ve 24 h por su aviso)
 *
 * @param {{ estado?: string, aviso?: { estado?: string } | null }} f
 * @returns {{ grupo: 'activa' | 'avisando' | 'resuelta', texto: string, tono: 'critico' | 'alerta' | 'accion' | 'ok' }}
 */
export function estadoDeLaCaida(f) {
  const estado = String(f?.estado ?? '');
  const legible = ESTADO_LEGIBLE[estado] ?? estado;
  if (f?.aviso?.estado === 'en_curso') return { grupo: 'avisando', texto: `${legible} · avisando`, tono: 'accion' };
  if (VIVOS.has(estado)) return { grupo: 'activa', texto: `Activa · ${legible.toLowerCase()}`, tono: 'critico' };
  if (estado === 'en_verificacion') return { grupo: 'activa', texto: legible, tono: 'alerta' };
  return { grupo: 'resuelta', texto: legible, tono: 'ok' };
}

/**
 * Los cuatro números de arriba.
 * @param {any[]} fallas
 */
export function resumenDeFallas(fallas) {
  const lista = Array.isArray(fallas) ? fallas : [];
  const vivas = lista.filter((f) => VIVOS.has(String(f?.estado ?? '')));
  const enviando = lista.filter((f) => f?.aviso?.estado === 'en_curso');
  return {
    activas: vivas.length,
    //  Solo las vivas: una restablecida ya no tiene equipos afectados.
    equipos: vivas.reduce((s, f) => s + (Number(f?.equipos) || 0), 0),
    avisando: enviando.length,
    avisados: enviando.reduce((s, f) => s + (Number(f?.aviso?.enviados) || 0), 0),
    aprobados: enviando.reduce((s, f) => s + (Number(f?.aviso?.clientes) || 0), 0),
    resueltas: lista.filter((f) => estadoDeLaCaida(f).grupo === 'resuelta').length
  };
}

/**
 * «2 h 58 min», «12 min», «1 d 3 h». Vacío si no hay fecha.
 * @param {string | null | undefined} desdeIso
 * @param {number} [ahora]
 */
export function duracion(desdeIso, ahora = Date.now()) {
  const t = desdeIso ? Date.parse(desdeIso) : NaN;
  if (!Number.isFinite(t)) return '';
  const min = Math.max(0, Math.round((ahora - t) / 60000));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ${min % 60} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}
