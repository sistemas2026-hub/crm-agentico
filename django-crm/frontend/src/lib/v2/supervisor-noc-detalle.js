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

/**
 * La antigüedad del caso, si la evidencia la trae.
 *
 * El detector escribe una observación con la forma
 * `abierto desde 2026-09-15 (7 dias)`. Se leen las dos partes; si el texto no
 * coincide, devuelve null y el bloque no se dibuja.
 *
 * @param {any[] | null | undefined} evidencia
 * @returns {{desde: string, dias: number|null} | null}
 */
export function antiguedadDelCaso(evidencia) {
  if (!Array.isArray(evidencia)) return null;
  const hit = evidencia.find((e) => /^abierto desde\s/i.test(String(e?.dato ?? '')));
  if (!hit) return null;
  const texto = String(hit.dato);
  const fecha = texto.match(/(\d{4}-\d{2}-\d{2})/)?.[1];
  if (!fecha) return null;
  const dias = texto.match(/\((\d+)\s*d/i)?.[1];
  return { desde: fecha, dias: dias ? Number(dias) : null };
}

/**
 * Cuándo se leyó por última vez el estado del lado del proveedor.
 *
 * Es distinto de `observado_en`: ese dice cuándo el detector miró su propia
 * base; este, cuándo se consultó al tercero. La diferencia importa cuando hay
 * que decidir si el dato externo todavía sirve.
 *
 * @param {any[] | null | undefined} evidencia
 */
export function lecturaExterna(evidencia) {
  if (!Array.isArray(evidencia)) return null;
  const hit = evidencia.find((e) => /estado externo le[ií]do/i.test(String(e?.dato ?? '')));
  if (!hit) return null;
  const m = String(hit.dato).match(/le[ií]do el\s+(.+)$/i);
  return m ? m[1].trim() : null;
}

/**
 * Los datos del contexto operativo que el backend NO entrega hoy.
 *
 * Se declaran en un solo lugar para que la pantalla pueda decir cuáles faltan
 * en vez de dibujar cuatro casillas vacías o, peor, inventarlas. Cuando el
 * serializer los exponga, se sacan de esta lista y el bloque los muestra.
 */
export const CONTEXTO_AUSENTE = [
  'SLA del caso',
  'Última actividad registrada',
  'Último compromiso pendiente',
  'Responsable actual'
];

/**
 * Las etapas del ciclo, y en cuál está la propuesta.
 *
 * LAS TRES ÚLTIMAS NO EXISTEN TODAVÍA, y se muestran a propósito: el diseño
 * las pedía, y dibujarlas apagadas es la forma más clara de decir dónde
 * termina lo que esta etapa del producto puede hacer. El estado «ejecutada»
 * no está en el modelo (operaciones/models.py lo dice con todas las letras:
 * aceptar significa «el Jefe de Operaciones está de acuerdo», no «se hizo»).
 *
 * Devuelve cada paso con su estado visual: 'hecho', 'actual' o 'inactivo'.
 *
 * @param {string | null | undefined} estado  el estado real de la propuesta
 */
export function pasosDelCiclo(estado) {
  const revisada = ['aceptada', 'modificada', 'rechazada', 'cancelada', 'expirada'].includes(
    String(estado)
  );
  const aprobada = ['aceptada', 'modificada'].includes(String(estado));

  return [
    {
      clave: 'propuesta',
      texto: 'Propuesta',
      estado: estado === 'propuesta' ? 'actual' : 'hecho'
    },
    {
      clave: 'revisada',
      texto: 'Revisada',
      estado: revisada ? (aprobada ? 'hecho' : 'actual') : 'inactivo'
    },
    {
      clave: 'aprobada',
      texto: 'Aprobada',
      estado: aprobada ? 'actual' : 'inactivo'
    },
    // De aquí en adelante no hay nada: ninguna de las tres es alcanzable.
    { clave: 'encolada', texto: 'Encolada', estado: 'inactivo' },
    { clave: 'ejecutada', texto: 'En ejecución', estado: 'inactivo' },
    { clave: 'validada', texto: 'Validada', estado: 'inactivo' }
  ];
}

/* ===========================================================================
   LA LECTURA HUMANA DEL HALLAZGO
   ===========================================================================
   Todo lo que sigue traduce lo que el backend YA entrega a lo que una persona
   necesita para decidir. Ninguna de estas funciones consulta nada ni calcula
   un hecho nuevo: reordenan y nombran.

   LA REGLA QUE LAS ATRAVIESA
   --------------------------
   Un dato que la fuente no trae se DICE, no se rellena. Por eso existe
   AUSENTE: un guion deja al lector sin saber si el dato no aplica, no llegó o
   nadie lo cargó, y esas tres cosas se arreglan en sitios distintos.
   =========================================================================== */

export const AUSENTE = 'No disponible en la fuente';

const hay = (v) => v !== null && v !== undefined && String(v).trim() !== '';
const oAusente = (v) => (hay(v) ? String(v) : AUSENTE);

/**
 * Cómo se nombra cada señal de cara al usuario.
 *
 * La clave técnica NO cambia en el backend: esto es solo el rótulo. Un tipo
 * que no esté aquí cae en su `tipo_senal_display`, que el backend ya traduce.
 */
export const NOMBRE_HUMANO = {
  caso_desincronizado: 'Desincronización WispHub ↔ Dexter',
  caso_abierto_antiguo: 'Caso abierto sin avance registrado',
  orden_sin_programar: 'Orden sin programación',
  orden_sla_vencido: 'Orden con plazo vencido',
  orden_sla_por_vencer: 'Orden con plazo por vencer'
};

/** @param {any} d  la propuesta en detalle */
export function nombreHumano(d) {
  if (!d) return AUSENTE;
  return NOMBRE_HUMANO[d.tipo_senal] ?? d.tipo_senal_display ?? d.tipo_senal ?? AUSENTE;
}

/**
 * «¿Qué está pasando?», en una frase.
 *
 * Se arma por tipo de señal y se apoya en la EVIDENCIA real cuando la hay: la
 * frase de desincronización nombra el estado que el proveedor reportó, no uno
 * supuesto. Un tipo sin frase propia cae en el motivo que escribió el
 * Supervisor, que siempre existe.
 *
 * @param {any} d
 * @param {any} [contraste]
 */
export function quePasa(d, contraste) {
  if (!d) return AUSENTE;
  const c = contraste ?? contrasteDeEstados(d.evidencia);
  if (d.tipo_senal === 'caso_desincronizado') {
    const externo = hay(c?.proveedor) ? `como «${c.proveedor}»` : 'como cerrado';
    const interno = hay(c?.crm) ? `«${c.crm}»` : 'abierto';
    return `WispHub registra el ticket ${externo} mientras el caso en Dexter sigue en ${interno}.`;
  }
  if (d.tipo_senal === 'caso_abierto_antiguo') {
    return 'El caso lleva tiempo abierto en Dexter y no consta ninguna respuesta registrada.';
  }
  return d.motivo || AUSENTE;
}

/**
 * La prioridad, en lenguaje humano.
 *
 * NO se inventa un corte sobre el número: el rango real medido es 30–42 y un
 * umbral tipo «≥50 = alta» pondría todo en la misma casilla. Lo que sí es
 * semántico es el NIVEL de autonomía que el backend exige (0 observar ·
 * 1 recomendar), y sobre él se decide; el número sigue visible al lado.
 *
 * @param {any} d
 */
export function prioridadHumana(d) {
  if (!d || !hay(d.prioridad)) return { texto: AUSENTE, tono: 'neutro', icono: '' };
  if (d.nivel_autonomia_requerido === 0) {
    return { texto: 'Baja', tono: 'ok', icono: '🟢', n: d.prioridad };
  }
  if (d.prioridad >= 42) return { texto: 'Alta', tono: 'critico', icono: '🔴', n: d.prioridad };
  if (d.prioridad >= 38) return { texto: 'Media', tono: 'alerta', icono: '🟠', n: d.prioridad };
  return { texto: 'Baja', tono: 'ok', icono: '🟢', n: d.prioridad };
}

/**
 * Las cuatro casillas de identificación del encabezado.
 *
 * `contexto` es la fila de la tabla, que YA trae ticket y proveedor resueltos
 * por el backend (contexto_propuesta.py). No se vuelve a pedir nada.
 *
 * MEDIDO el 25/09/2026: ninguno de los 237 casos de producción tiene cuenta
 * asociada (`account_id` nulo en todos) y el asunto del ticket no viaja en el
 * detalle. Las dos casillas dicen que el dato no está, en vez de vaciarse.
 *
 * @param {any} d
 * @param {any} [contexto]
 */
export function identificacion(d, contexto) {
  const ctx = contexto ?? {};
  return [
    { rotulo: 'Cliente', valor: oAusente(ctx.cliente) },
    {
      rotulo: 'Caso Dexter',
      valor: d?.origen_id ? `CS-${String(d.origen_id).slice(0, 8)}` : AUSENTE,
      href: d?.origen_tipo === 'case' && d?.origen_id ? `/tickets/${d.origen_id}` : null
    },
    { rotulo: 'Ticket WispHub', valor: oAusente(ctx.ticket_externo) },
    { rotulo: 'Asunto del ticket', valor: oAusente(ctx.asunto) }
  ];
}

/**
 * La comparación Dexter ↔ WispHub, fila por fila.
 *
 * Sale de la EVIDENCIA que el propio hallazgo guardó y del contexto de la
 * fila. Ninguna celda se rellena por simetría: si una fuente no entregó el
 * dato, lo dice.
 *
 * Ojo con la fila de lectura: del proveedor solo se sabe CUÁNDO SE LEYÓ
 * (`external_fetched_at`), no cuándo cambió allá. Se rotula como lectura para
 * no prometer una marca de cambio que nadie tiene.
 *
 * @param {any} d
 * @param {any} [contexto]
 */
export function comparacionFuentes(d, contexto) {
  const ctx = contexto ?? {};
  const c = contrasteDeEstados(d?.evidencia);
  const lectura = lecturaExterna(d?.evidencia);
  const ant = antiguedadDelCaso(d?.evidencia);

  return [
    { campo: 'Estado', dexter: oAusente(c?.crm), wisphub: oAusente(c?.proveedor) },
    {
      campo: 'Identificador',
      dexter: d?.origen_id ? `CS-${String(d.origen_id).slice(0, 8)}` : AUSENTE,
      wisphub: oAusente(ctx.ticket_externo)
    },
    {
      campo: 'Última lectura',
      //  'antiguedadDelCaso' devuelve {desde, dias} y 'lecturaExterna' una
      //  cadena: se usan tal como son, sin envolverlas en otra forma.
      dexter: ant?.desde ? `Abierto desde ${ant.desde}` : AUSENTE,
      wisphub: oAusente(lectura)
    },
    {
      campo: 'Responsable',
      //  'tecnico' del contexto es quien TIENE la orden asignada; para un caso
      //  viene vacío, y eso es un dato ausente, no «sin asignar».
      dexter: oAusente(ctx.tecnico),
      wisphub: AUSENTE
    }
  ];
}

/**
 * El análisis, partido en las tres cosas que no deben confundirse.
 *
 * El Supervisor escribe 'motivo' (lo observado y su lectura) e 'impacto' (la
 * consecuencia). Aquí se presentan separados y se nombra lo que NO se sabe,
 * que es la parte que un lector apurado da por cierta.
 *
 * @param {any} d
 */
export function analisisSeparado(d) {
  const evidencia = Array.isArray(d?.evidencia) ? d.evidencia : [];
  return {
    hechos: evidencia
      .filter((e) => e?.fuente !== 'calculo_prioridad')
      .map((e) => ({ dato: e?.dato ?? '', fuente: e?.fuente ?? '', cuando: e?.observado_en ?? null })),
    interpretacion: d?.motivo || AUSENTE,
    impacto: d?.impacto || AUSENTE,
    faltantes: evidencia
      .map((e) => String(e?.dato ?? ''))
      .filter((t) => /falta|no consta|no se pudo|sin registrar|no dice/i.test(t))
  };
}

/**
 * «¿Qué pasa si acepto?» — el efecto REAL, no el deseado.
 *
 * Aceptar registra que el Jefe de Operaciones está de acuerdo. NO cierra el
 * caso, no toca WispHub y no ejecuta nada: el estado «ejecutada» no existe en
 * el modelo y `ejecutar_propuesta` levanta siempre. Poner aquí «resultado:
 * Dexter cerrado» prometería una ejecución que el sistema no hace, y esta
 * pantalla es justo donde ese malentendido saldría caro.
 *
 * @param {any} d
 * @param {any} [contraste]
 */
export function siAcepto(d, contraste) {
  const c = contraste ?? contrasteDeEstados(d?.evidencia);
  return {
    estadoActual: oAusente(c?.crm),
    //  Lo que la propuesta pide hacer, con sus palabras. No se traduce a un
    //  estado final: la acción de H-15 es REVISAR la sincronización, no cerrar.
    accion: d?.accion_propuesta || AUSENTE,
    origenDecision: hay(c?.proveedor) ? 'WispHub' : AUSENTE,
    tipo: 'Revisión humana · propuesta del Supervisor NOC IA',
    efecto:
      'Queda registrado que estás de acuerdo. No cierra el caso, no toca WispHub y no ' +
      'ejecuta ninguna acción: en esta etapa el Supervisor observa y propone.',
    requiereConfirmacion: true
  };
}
