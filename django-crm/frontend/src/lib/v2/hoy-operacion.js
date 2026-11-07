/**
 * La portada "Hoy de la operacion": que le pide la operacion a una persona
 * AHORA, en una sola cola.
 *
 * Hasta el 23/10/2026 la portada era la de BottleCRM: tickets sin primera
 * respuesta, facturas vencidas, negociaciones frias y tareas. Nada de lo que
 * mueve a un ISP -- un cliente esperando a una persona, una orden detenida
 * esperando al NOC, una instalacion por decidir, un pedido de bodega -- llegaba
 * a la pantalla que se abre primero. Esto junta las dos cosas.
 *
 * EL CODIGO CALCULA (PRD §12.5)
 * Cuantas son, cual es la mas vieja, cuanto del plazo se consumio y en que
 * orden van: todo aca, sin modelo. La pantalla solo dibuja.
 *
 * "VENCIDO" SOLO DONDE HAY UN PLAZO DE VERDAD
 * Tres tonos, y el primero se gana, no se supone:
 *   'urg'    paso su plazo. Solo existe donde hay un plazo configurado: la toma
 *            de conversaciones (sla_toma_minutos del tenant) y lo que el CRM
 *            ya marca como vencido (su SLA de primera respuesta, facturas).
 *   'aten'   necesita a alguien ahora, pero nadie definio un plazo: un bloqueo
 *            esperando al NOC, una instalacion por decidir, un pedido. Pintarlos
 *            de rojo seria inventar un vencimiento que nadie fijo.
 *   'neutro' puede esperar.
 *
 * Funcion pura: entra lo que devolvio cada fuente (o null si no se pudo leer),
 * sale la cola. Se prueba sin red en hoy-operacion.test.js.
 */

/** @typedef {'urg' | 'aten' | 'neutro'} Tono */

/**
 * @typedef {{
 *   id: string,
 *   origen: string,
 *   icono: 'conversacion' | 'noc' | 'instalacion' | 'bodega' | 'ticket' | 'factura' | 'negociacion' | 'tarea',
 *   tono: Tono,
 *   cuando: string,
 *   titulo: string,
 *   detalle: string,
 *   accion: string,
 *   href: string,
 *   minutos: number | null,
 *   plazo: { uso: number, texto: string } | null
 * }} Item
 */

const ORDEN_TONO = { urg: 0, aten: 1, neutro: 2 };

/** Minutos entre una marca ISO y `ahora`, o null si no hay marca. */
export function minutosDesde(iso, ahora) {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((ahora - t) / 60000));
}

/** "18 min", "1 h 20 min", "2 días". */
export function duracion(min) {
  if (min == null) return '';
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) {
    const resto = min % 60;
    return resto ? `${h} h ${resto} min` : `${h} h`;
  }
  const d = Math.floor(h / 24);
  return d === 1 ? '1 día' : `${d} días`;
}

const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

/** La mas vieja de una lista, por minutos de espera. */
function masVieja(filas, minutosDe) {
  let mejor = null;
  let min = -1;
  for (const f of filas) {
    const m = minutosDe(f);
    if (m != null && m > min) {
      mejor = f;
      min = m;
    }
  }
  return { fila: mejor, minutos: min >= 0 ? min : null };
}

/**
 * Las conversaciones que piden una persona, por banda del motor
 * (nucleo/relevo/proyeccion.py): 1 cliente_espera, 2 sin_asignar, 3 revisar.
 */
function deConversaciones(conversaciones, slaMin, ahora) {
  /** @type {Item[]} */
  const items = [];
  const porBanda = (b) => conversaciones.filter((c) => c.banda === b);
  const minutosDe = (c) => minutosDesde(c.esperando_desde, ahora);

  const conPlazo = (min) => {
    if (!slaMin || min == null) return { tono: /** @type {Tono} */ ('aten'), plazo: null };
    const uso = Math.min(100, Math.round((min / slaMin) * 100));
    return {
      tono: /** @type {Tono} */ (min > slaMin ? 'urg' : 'aten'),
      plazo: { uso, texto: `${duracion(min)} de ${duracion(slaMin)}` }
    };
  };

  const espera = porBanda(1);
  if (espera.length) {
    const { fila, minutos } = masVieja(espera, minutosDe);
    const { tono, plazo } = conPlazo(minutos);
    const una = espera.length === 1;
    items.push({
      id: 'conv-espera',
      origen: 'Conversaciones',
      icono: 'conversacion',
      tono,
      cuando: minutos != null ? `${una ? 'Espera' : 'La más vieja'} hace ${duracion(minutos)}` : 'Esperando',
      titulo: una
        ? 'Un cliente espera respuesta de una persona'
        : `${espera.length} clientes esperan respuesta de una persona`,
      detalle: (una ? fila?.motivo_cola : null) || 'Dexter ya les avisó que una persona los va a atender.',
      accion: una ? 'Tomar conversación' : 'Ver conversaciones',
      href: una && fila?.id ? `/conversaciones/${fila.id}` : '/conversaciones',
      minutos,
      plazo
    });
  }

  const sinAsignar = porBanda(2);
  if (sinAsignar.length) {
    const { minutos } = masVieja(sinAsignar, minutosDe);
    const { tono, plazo } = conPlazo(minutos);
    items.push({
      id: 'conv-sin-asignar',
      origen: 'Conversaciones',
      icono: 'conversacion',
      tono,
      cuando: minutos != null ? `La más vieja: ${duracion(minutos)}` : 'Sin asignar',
      titulo: `${plural(sinAsignar.length, 'conversación escalada', 'conversaciones escaladas')} sin asignar`,
      detalle: 'Nadie las tomó todavía.',
      accion: 'Asignar',
      href: '/conversaciones',
      minutos,
      plazo
    });
  }

  const revisar = porBanda(3);
  if (revisar.length) {
    const { minutos } = masVieja(revisar, minutosDe);
    items.push({
      id: 'conv-revisar',
      origen: 'Conversaciones',
      icono: 'conversacion',
      tono: 'neutro',
      cuando: minutos != null ? `Desde hace ${duracion(minutos)}` : 'Para revisar',
      titulo: `${plural(revisar.length, 'conversación', 'conversaciones')} para revisar`,
      detalle: 'Quedaron sin gestión o con una evaluación pendiente.',
      accion: 'Revisar',
      href: '/conversaciones',
      minutos,
      plazo: null
    });
  }
  return items;
}

/** Bloqueos de campo que esperan al NOC (requiere_noc). */
function deBloqueos(bloqueos) {
  const noc = bloqueos.filter((b) => b.requiere_noc);
  if (!noc.length) return [];
  const { fila, minutos } = masVieja(noc, (b) => (typeof b.minutos_detenido === 'number' ? b.minutos_detenido : null));
  const una = noc.length === 1;
  return [
    {
      id: 'noc-bloqueos',
      origen: 'NOC',
      icono: 'noc',
      tono: 'aten',
      cuando: minutos != null ? `${una ? 'Detenida' : 'La más vieja'} hace ${duracion(minutos)}` : 'Detenida',
      titulo: una
        ? 'Una orden está detenida esperando al NOC'
        : `${noc.length} órdenes detenidas esperando al NOC`,
      detalle: (una ? fila?.motivo : null) || 'El plazo de cada orden queda en pausa hasta que el NOC responda.',
      accion: 'Revisar bloqueo',
      href: '/supervisor-noc',
      minutos,
      plazo: null
    }
  ];
}

/** Solicitudes de instalacion en ENVIADA: esperan decision de factibilidad. */
function deSolicitudes(solicitudes, ahora) {
  if (!solicitudes.length) return [];
  const { minutos } = masVieja(solicitudes, (s) => minutosDesde(s.enviada_en, ahora));
  return [
    {
      id: 'instalaciones',
      origen: 'Instalaciones',
      icono: 'instalacion',
      tono: 'aten',
      cuando: minutos != null ? `La más vieja: ${duracion(minutos)}` : 'Por decidir',
      titulo: `${plural(solicitudes.length, 'solicitud', 'solicitudes')} de instalación por decidir`,
      detalle: 'Esperan que alguien confirme la factibilidad antes de crear el ticket.',
      accion: 'Decidir factibilidad',
      href: '/instalaciones',
      minutos,
      plazo: null
    }
  ];
}

/** Pedidos de material a bodega todavia sin resolver. */
function dePedidos(pedidos, ahora) {
  const pendientes = pedidos.filter((p) => p.estado === 'pendiente');
  if (!pendientes.length) return [];
  const { minutos } = masVieja(pendientes, (p) => minutosDesde(p.en, ahora));
  return [
    {
      id: 'bodega-pedidos',
      origen: 'Bodega',
      icono: 'bodega',
      tono: 'aten',
      cuando: minutos != null ? `El más viejo: ${duracion(minutos)}` : 'Sin resolver',
      titulo: `${plural(pendientes.length, 'pedido', 'pedidos')} de material sin resolver`,
      detalle: 'Una cuadrilla espera material para terminar un trabajo.',
      accion: 'Resolver pedidos',
      href: '/inventario?ver=reportes&de=pedidos',
      minutos,
      plazo: null
    }
  ];
}

const TONO_CRM = { rust: 'urg', clay: 'aten', slate: 'neutro', moss: 'neutro' };

/** De que modulo viene un item del CRM, por su ruta (la arma el servidor). */
function origenCrm(href = '') {
  if (href.startsWith('/tickets')) return { origen: 'Tickets', icono: 'ticket' };
  if (href.startsWith('/invoices')) return { origen: 'Facturas', icono: 'factura' };
  if (href.startsWith('/pipeline') || href.startsWith('/opportunit')) return { origen: 'Negociaciones', icono: 'negociacion' };
  return { origen: 'Tareas', icono: 'tarea' };
}

/** La cola que ya armaba /dashboard/today/ (tickets, facturas, negociaciones, tareas). */
function deCrm(queue) {
  return queue.map((q) => ({
    id: `crm-${q.id}`,
    ...origenCrm(q.href),
    tono: /** @type {Tono} */ (TONO_CRM[q.tone] ?? 'neutro'),
    cuando: q.due ?? '',
    titulo: q.title,
    detalle: q.detail ?? '',
    accion: q.action ?? 'Abrir',
    href: q.href,
    minutos: null,
    plazo: null
  }));
}

/**
 * @param {{
 *   conversaciones?: any[] | null,
 *   slaTomaMinutos?: number,
 *   bloqueos?: any[] | null,
 *   solicitudes?: any[] | null,
 *   pedidos?: any[] | null,
 *   crm?: any[] | null,
 *   ahora?: number
 * }} fuentes  null en una fuente = no se pudo leer (distinto de [] = no hay nada)
 * @returns {Item[]}
 */
export function armarCola(fuentes) {
  const ahora = fuentes.ahora ?? Date.now();
  const operacion = [
    ...deConversaciones(fuentes.conversaciones ?? [], fuentes.slaTomaMinutos ?? 0, ahora),
    ...deBloqueos(fuentes.bloqueos ?? []),
    ...deSolicitudes(fuentes.solicitudes ?? [], ahora),
    ...dePedidos(fuentes.pedidos ?? [], ahora)
  ];
  // La operacion se ordena aca: tono y, dentro del tono, quien espera hace mas.
  // La del CRM ya viene priorizada por el backend, y se respeta su orden
  // dentro de cada tono (el sort es estable).
  const crm = deCrm(fuentes.crm ?? []);
  const ordenOperacion = [...operacion].sort(
    (a, b) => ORDEN_TONO[a.tono] - ORDEN_TONO[b.tono] || (b.minutos ?? -1) - (a.minutos ?? -1)
  );
  return [...ordenOperacion, ...crm].sort((a, b) => ORDEN_TONO[a.tono] - ORDEN_TONO[b.tono]);
}

/**
 * La columna "Por area": cuantos hay en cada lugar, con enlace. Una fuente que
 * no se pudo leer (null) no aparece: un 0 ahi diria "no hay nada", que es
 * otra cosa que "no se sabe".
 *
 * @param {{ conversaciones?: any[] | null, bloqueos?: any[] | null,
 *           solicitudes?: any[] | null, pedidos?: any[] | null,
 *           crmFuentes?: { label: string, count: number, href: string }[] | null }} f
 */
export function armarPorArea(f) {
  /** @type {{ id: string, nombre: string, nota: string, valor: number, icono: string, href: string }[]} */
  const filas = [];
  if (f.conversaciones) {
    const n = f.conversaciones.filter((c) => c.banda === 1 || c.banda === 2 || c.banda === 3).length;
    filas.push({ id: 'conversaciones', nombre: 'Conversaciones', nota: 'piden una persona', valor: n, icono: 'conversacion', href: '/conversaciones' });
  }
  if (f.bloqueos) {
    const n = f.bloqueos.filter((b) => b.requiere_noc).length;
    filas.push({ id: 'noc', nombre: 'NOC', nota: 'órdenes detenidas', valor: n, icono: 'noc', href: '/supervisor-noc' });
  }
  if (f.solicitudes) {
    filas.push({ id: 'instalaciones', nombre: 'Instalaciones', nota: 'por decidir', valor: f.solicitudes.length, icono: 'instalacion', href: '/instalaciones' });
  }
  if (f.pedidos) {
    const n = f.pedidos.filter((p) => p.estado === 'pendiente').length;
    filas.push({ id: 'bodega', nombre: 'Bodega', nota: 'pedidos sin resolver', valor: n, icono: 'bodega', href: '/inventario?ver=reportes&de=pedidos' });
  }
  for (const s of f.crmFuentes ?? []) {
    const { origen, icono } = origenCrm(s.href);
    filas.push({ id: `crm-${s.href}`, nombre: origen, nota: s.label, valor: s.count, icono, href: s.href });
  }
  return filas;
}

/** Cuantos hay por tono, para los filtros y la frase de arriba. */
export function contarPorTono(cola) {
  const n = { urg: 0, aten: 0, neutro: 0 };
  for (const i of cola) n[i.tono] += 1;
  return n;
}

/** La frase de arriba. Se adapta a los numeros en vez de decir "0 cosas". */
export function resumen(cola) {
  if (!cola.length) return 'Nada te necesita ahora. Dexter sigue atendiendo.';
  const { urg } = contarPorTono(cola);
  const base = plural(cola.length, 'cosa te necesita ahora', 'cosas te necesitan ahora');
  const vencidas = urg ? `; ${plural(urg, 'ya pasó su plazo', 'ya pasaron su plazo')}` : '';
  return `${base}${vencidas}. Lo primero: ${cola[0].titulo.charAt(0).toLowerCase()}${cola[0].titulo.slice(1)}.`;
}
