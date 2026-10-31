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
  plantilla_no_coincide: 'La plantilla aprobada no coincide con los datos elegidos.'
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
  TOPE_DE_VUELTAS: 'Se agotaron los reintentos; los que faltaban no recibieron el aviso.'
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
