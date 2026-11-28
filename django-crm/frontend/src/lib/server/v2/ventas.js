/**
 * El embudo de ventas del ISP (12/11/2026).
 *
 * Link generado → formulario abierto → enviado → aprobado → instalado. Todos
 * los números los calcula Django (`leads/embudo.py`): acá no se suma, no se
 * cuenta y no se divide nada. Lo único que hace esta capa es traducir claves a
 * rótulos, decidir A DÓNDE lleva cada fila detenida y pasar una fracción a
 * porcentaje para mostrarla — formato, no cálculo.
 *
 * Dos etapas llegan sin número («chats de venta» y «activas»): el backend dice
 * por qué. Se muestran como «sin dato» con ese motivo, nunca como cero, porque
 * un cero se lee como «no hubo», y la verdad es «no lo sabemos medir todavía».
 *
 * Nunca lanza: no poder leer el embudo es un aviso en la pantalla, no un error
 * que tumba la navegación.
 */
import { apiRequest } from '$lib/api-helpers.js';

export const PERIODOS = [7, 30, 90];

export const ETIQUETA_ETAPA = {
  chats: 'Chats de venta',
  links: 'Links generados',
  abiertos: 'Formularios abiertos',
  enviadas: 'Formularios enviados',
  aprobadas: 'Aprobadas',
  instaladas: 'Instaladas',
  activas: 'Activas en el sistema del ISP',
  decision: 'Decisión'
};

export const ETIQUETA_DETENIDA = {
  sin_abrir: 'Link sin abrir',
  abierto_sin_enviar: 'Abrió el formulario y no lo envió',
  esperando_decision: 'Esperando decisión de factibilidad',
  aprobada_sin_instalar: 'Aprobada, sin instalar'
};

export const MOTIVO_SIN_INSTALAR = {
  sin_ticket: 'Sin ticket en el sistema del ISP',
  ticket_sin_caso: 'El ticket todavía no llegó como caso',
  caso_sin_orden: 'Caso sin orden de campo',
  orden_abierta: 'Orden de campo abierta'
};

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

/**
 * El periodo pedido en la URL, limpio. Lo que no se entiende cae a 30 días
 * acá, ANTES de preguntar: Django rechaza lo malformado con 400, y la pantalla
 * prefiere mostrar un periodo válido rotulado con su nombre real.
 * @param {URLSearchParams} sp
 */
export function periodoDe(sp) {
  const desde = sp.get('desde') ?? '';
  const hasta = sp.get('hasta') ?? '';
  if (FECHA.test(desde) && FECHA.test(hasta)) return { dias: null, desde, hasta };
  const dias = Number(sp.get('dias'));
  return { dias: PERIODOS.includes(dias) ? dias : 30, desde: '', hasta: '' };
}

/**
 * A dónde lleva una fila detenida. Lo decide el servidor, no la plantilla:
 * el mismo dato no puede llevar a dos lugares según quién lo dibuje.
 * @param {string} grupo
 * @param {any} f
 * @returns {{ href: string|null, texto: string }}
 */
export function destinoDe(grupo, f) {
  if (grupo === 'sin_abrir' || grupo === 'abierto_sin_enviar') {
    return f.lead_id
      ? { href: `/leads/${f.lead_id}`, texto: 'Ver prospecto' }
      : { href: null, texto: 'Sin prospecto asociado' };
  }
  if (grupo === 'esperando_decision') return { href: '/instalaciones', texto: 'Decidir en Instalaciones' };
  if (f.caso_id) return { href: `/tickets/${f.caso_id}`, texto: 'Ver ticket' };
  return { href: '/instalaciones?estado=aprobada', texto: 'Ver en Instalaciones' };
}

/** @param {number|null|undefined} tasa */
function porcentaje(tasa) {
  return typeof tasa === 'number' ? Math.round(tasa * 1000) / 10 : null;
}

/**
 * @param {any} cookies
 * @param {{ dias: number|null, desde: string, hasta: string }} periodo
 */
export async function leerEmbudo(cookies, periodo) {
  const q = periodo.dias
    ? `?dias=${periodo.dias}`
    : `?desde=${encodeURIComponent(periodo.desde)}&hasta=${encodeURIComponent(periodo.hasta)}`;
  /** @type {any} */
  let d;
  try {
    d = await apiRequest(`/leads/embudo/${q}`, {}, cookies);
  } catch (/** @type {any} */ err) {
    const sinPermiso = err?.status === 403;
    return {
      periodo,
      error: sinPermiso
        ? 'El embudo de ventas lo ven administración y los roles de gestión.'
        : err?.message || 'No se pudo leer el embudo de ventas.',
      sinPermiso,
      etapas: [],
      pasos: [],
      tiempos: [],
      caidas: null,
      detenidas: [],
      instalacionSinDato: 0
    };
  }
  const conteos = d?.conteos ?? {};
  const sinDato = d?.sin_dato ?? {};
  // El largo de cada barra, relativo a los links generados. Es dibujo, no
  // dato: el número que se lee al lado es el que mandó Django.
  const base = typeof conteos.links === 'number' && conteos.links > 0 ? conteos.links : 0;
  return {
    periodo,
    error: null,
    sinPermiso: false,
    etapas: (d?.etapas ?? []).map((/** @type {string} */ clave) => ({
      clave,
      etiqueta: ETIQUETA_ETAPA[/** @type {keyof typeof ETIQUETA_ETAPA} */ (clave)] ?? clave,
      valor: typeof conteos[clave] === 'number' ? conteos[clave] : null,
      sinDato: typeof conteos[clave] === 'number' ? null : (sinDato[clave] ?? 'Sin dato.'),
      // Qué fracción llegó acá desde la etapa medible anterior (la calcula Django).
      pasoDesdeAnterior: porcentaje(
        (d?.pasos ?? []).find((/** @type {any} */ p) => p.a === clave)?.tasa
      ),
      barra:
        typeof conteos[clave] === 'number' && base ? Math.min(100, (conteos[clave] / base) * 100) : 0
    })),
    pasos: (d?.pasos ?? []).map((/** @type {any} */ p) => ({
      de: p.de,
      a: p.a,
      porcentaje: porcentaje(p.tasa)
    })),
    tiempos: (d?.tiempos ?? []).map((/** @type {any} */ t) => ({
      etiqueta: `${ETIQUETA_ETAPA[/** @type {keyof typeof ETIQUETA_ETAPA} */ (t.de)] ?? t.de} → ${
        ETIQUETA_ETAPA[/** @type {keyof typeof ETIQUETA_ETAPA} */ (t.a)] ?? t.a
      }`,
      horas: typeof t.horas === 'number' ? t.horas : null,
      muestras: t.muestras ?? 0
    })),
    caidas: d?.caidas ?? null,
    instalacionSinDato: d?.instalacion_sin_dato ?? 0,
    detenidas: Object.keys(ETIQUETA_DETENIDA).map((grupo) => {
      const g = d?.detenidas?.[grupo] ?? { total: 0, filas: [] };
      return {
        clave: grupo,
        etiqueta: ETIQUETA_DETENIDA[/** @type {keyof typeof ETIQUETA_DETENIDA} */ (grupo)],
        total: g.total ?? 0,
        filas: (g.filas ?? []).map((/** @type {any} */ f) => ({
          ...f,
          motivoTexto: f.motivo
            ? (MOTIVO_SIN_INSTALAR[/** @type {keyof typeof MOTIVO_SIN_INSTALAR} */ (f.motivo)] ?? f.motivo)
            : null,
          destino: destinoDe(grupo, f)
        }))
      };
    })
  };
}

export const ETIQUETA_ESTADO_SOLICITUD = {
  nueva: 'Link generado',
  enviada: 'Formulario enviado',
  aprobada: 'Aprobada',
  sin_factibilidad: 'Sin factibilidad',
  cancelada: 'Cancelada'
};

/**
 * Lo que pasó con el link que el asistente le generó a un prospecto, para su
 * ficha. Nunca lanza: la ficha se dibuja igual sin este bloque.
 * @param {any} cookies
 * @param {string} leadId
 */
export async function leerSolicitudesDelLead(cookies, leadId) {
  try {
    const d = await apiRequest(`/leads/${encodeURIComponent(leadId)}/solicitud/`, {}, cookies);
    return {
      error: null,
      solicitudes: (d?.solicitudes ?? []).map((/** @type {any} */ s) => ({
        ...s,
        estadoTexto:
          ETIQUETA_ESTADO_SOLICITUD[/** @type {keyof typeof ETIQUETA_ESTADO_SOLICITUD} */ (s.estado)] ??
          s.estado,
        abierta: Boolean(s.abierta_en),
        hrefInstalaciones:
          s.estado === 'enviada' || s.estado === 'aprobada'
            ? `/instalaciones${s.estado === 'aprobada' ? '?estado=aprobada' : ''}`
            : null,
        // La conversación se alcanza por el ticket: la solicitud no guarda de
        // qué chat vino, solo el teléfono, y la ficha del ticket sí la abre.
        hrefTicket: s.caso_id ? `/tickets/${s.caso_id}` : null
      }))
    };
  } catch (/** @type {any} */ err) {
    return { error: err?.message || 'No se pudo leer la solicitud.', solicitudes: [] };
  }
}
