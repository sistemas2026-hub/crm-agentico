/**
 * El tablero del Supervisor NOC IA: lo que cada bloque de la pantalla necesita,
 * derivado del árbol de `/api/operaciones/indicadores/` y de las propuestas.
 *
 * Vive fuera del componente para poder probarse: son reglas con casos borde
 * —indicadores que no llegan, señales que no existen, totales en cero— y
 * dentro del `.svelte` solo se podrían ejercitar montándolo.
 *
 * NINGUNA INVENTA UN DATO. Cuando el backend no entrega algo, la función
 * devuelve `{ disponible: false }` y la pantalla lo dice en lugar de dibujar
 * un cero. La diferencia entre «no hay» y «no se sabe» es la razón de ser de
 * casi todo este archivo.
 */

/** Lee `arbol.a.b.c` sin reventar en el camino. */
function en(arbol, ruta) {
  let n = arbol;
  for (const p of ruta) {
    if (n == null || typeof n !== 'object') return null;
    n = n[p];
  }
  return n;
}

/** El valor de un indicador con sobre, o null si no llegó. */
function valor(arbol, ruta) {
  const n = en(arbol, ruta);
  return n && typeof n === 'object' && 'valor' in n ? n.valor : null;
}

/**
 * Los seis KPI de la cabecera.
 *
 * Los dos primeros son DISTINTOS y no deben confundirse: «hallazgos actuales»
 * son señales vivas que el detector ve ahora; «propuestas pendientes» son las
 * que ya quedaron escritas esperando revisión. Que no coincidan es normal —
 * una señal repetida no vuelve a proponerse.
 *
 * Los otros cuatro salen de `senales_por_tipo`, que solo lista las señales
 * con al menos una ocurrencia: con el árbol presente, una clave ausente es un
 * cero real.
 *
 * @param {any} indicadores  el árbol de /indicadores/, o null
 * @param {any[]} propuestas
 */
export function kpisDelTablero(indicadores, propuestas) {
  const hay = !!en(indicadores, ['supervisor']);
  const porTipo = (tipo) => {
    if (!hay) return null;
    const v = valor(indicadores, ['supervisor', 'senales_por_tipo', tipo]);
    return v == null ? 0 : v;
  };
  const suma = (...tipos) => {
    if (!hay) return null;
    return tipos.reduce((t, x) => t + (porTipo(x) ?? 0), 0);
  };

  const pendientes = Array.isArray(propuestas)
    ? propuestas.filter((p) => p?.estado === 'propuesta').length
    : null;

  return [
    {
      clave: 'hallazgos',
      n: hay ? valor(indicadores, ['supervisor', 'senales_vigentes']) : null,
      titulo: 'Hallazgos actuales',
      sub: 'Detección en vivo',
      tono: 'critico'
    },
    {
      clave: 'propuestas',
      n: pendientes,
      titulo: 'Propuestas pendientes',
      sub: 'Requieren revisión',
      tono: 'info'
    },
    {
      clave: 'sla',
      n: suma('orden_sla_por_vencer', 'orden_sla_vencido'),
      titulo: 'SLA en riesgo',
      sub: 'Próximos a vencer',
      tono: 'alerta'
    },
    {
      clave: 'sin_programar',
      n: porTipo('orden_sin_programar'),
      titulo: 'Órdenes sin programar',
      sub: 'Requieren programación',
      tono: 'teal'
    },
    {
      clave: 'bloqueados',
      n: suma('actividad_bloqueada', 'dependencia_pendiente'),
      titulo: 'Casos bloqueados',
      sub: 'Con impedimentos',
      tono: 'critico'
    },
    {
      clave: 'desinc',
      n: porTipo('caso_desincronizado'),
      titulo: 'Desincronizaciones',
      sub: 'WispHub ↔ Dexter',
      tono: 'info'
    }
  ];
}

/** La paleta del donut, en el orden en que se reparten los tipos. */
const COLORES = ['#f97316', '#f59e0b', '#fbbf24', '#ef4444', '#ec4899', '#a855f7', '#94a3b8'];

/**
 * El donut «Hallazgos por tipo»: los seis tipos con más propuestas y un
 * «Otros» que recoge la cola, con sus tramos ya calculados.
 *
 * Se arma sobre las PROPUESTAS y no sobre `senales_por_tipo` porque el donut
 * acompaña a la tabla de abajo: los dos tienen que sumar lo mismo, o el
 * gráfico contradice a la lista que tiene al lado.
 *
 * @param {any[]} propuestas
 */
export function hallazgosPorTipo(propuestas) {
  if (!Array.isArray(propuestas) || propuestas.length === 0) {
    return { disponible: false, total: 0, tramos: [] };
  }

  const cuenta = new Map();
  for (const p of propuestas) {
    const previo = cuenta.get(p.tipo_senal);
    cuenta.set(p.tipo_senal, {
      etiqueta: p.tipo_senal_display ?? p.tipo_senal,
      n: (previo?.n ?? 0) + 1
    });
  }

  const orden = [...cuenta.entries()].sort((a, b) => b[1].n - a[1].n);
  const visibles = orden.slice(0, 6).map(([clave, v]) => ({ clave, ...v }));
  const resto = orden.slice(6).reduce((t, [, v]) => t + v.n, 0);
  if (resto > 0) visibles.push({ clave: 'otros', etiqueta: 'Otros', n: resto });

  const total = propuestas.length;
  let acumulado = 0;
  const tramos = visibles.map((v, i) => {
    const pct = (v.n / total) * 100;
    const tramo = {
      ...v,
      color: COLORES[i % COLORES.length],
      pct: Math.round(pct),
      // El donut se dibuja con stroke-dasharray sobre un círculo de
      // circunferencia 100: cada tramo ocupa su porcentaje y arranca donde
      // terminó el anterior.
      dash: `${pct.toFixed(2)} ${(100 - pct).toFixed(2)}`,
      offset: `${(-acumulado).toFixed(2)}`
    };
    acumulado += pct;
    return tramo;
  });

  return { disponible: true, total, tramos };
}

/**
 * El donut «Tickets por origen», de `indicadores_casos.por_origen`.
 *
 * El backend agrupa por `external_provider`: 'wisphub' cuando el caso espeja
 * un ticket del proveedor, y la clave 'dexter' cuando nació en el CRM. Los
 * rótulos de aquí traducen esas claves y NADA MÁS -- no se derivan categorías
 * que el campo no distinga.
 *
 * @param {any} indicadores
 */
export function ticketsPorOrigen(indicadores) {
  const porOrigen = en(indicadores, ['casos', 'por_origen']);
  if (!porOrigen || typeof porOrigen !== 'object') {
    return { disponible: false, total: 0, tramos: [] };
  }

  const filas = Object.entries(porOrigen)
    .map(([clave, v]) => ({
      clave,
      n: typeof v === 'object' && v && 'valor' in v ? v.valor : v
    }))
    .filter((f) => typeof f.n === 'number' && f.n > 0);

  const total = filas.reduce((t, f) => t + f.n, 0);
  if (total === 0) return { disponible: false, total: 0, tramos: [] };

  const COLOR = { wisphub: '#2563eb', dexter: '#93ccff' };
  const ROTULO = { wisphub: 'WispHub', dexter: 'Dexter' };

  let acumulado = 0;
  const tramos = filas
    .sort((a, b) => b.n - a.n)
    .map((f, i) => {
      const pct = (f.n / total) * 100;
      const tramo = {
        ...f,
        etiqueta: ROTULO[f.clave] ?? f.clave,
        color: COLOR[f.clave] ?? COLORES[i % COLORES.length],
        pct: Math.round(pct),
        dash: `${pct.toFixed(2)} ${(100 - pct).toFixed(2)}`,
        offset: `${(-acumulado).toFixed(2)}`
      };
      acumulado += pct;
      return tramo;
    });

  return { disponible: true, total, tramos };
}

/**
 * Las barras «Estado de casos técnicos», de `indicadores_casos.por_estado`.
 *
 * La altura se calcula contra el mayor: sin eso, seis barras de alturas
 * parecidas no dicen nada.
 *
 * @param {any} indicadores
 */
export function estadoDeCasos(indicadores) {
  const porEstado = en(indicadores, ['casos', 'por_estado']);
  if (!porEstado || typeof porEstado !== 'object') {
    return { disponible: false, barras: [] };
  }

  const filas = Object.entries(porEstado)
    .map(([estado, v]) => ({
      estado,
      n: typeof v === 'object' && v && 'valor' in v ? v.valor : v
    }))
    .filter((f) => typeof f.n === 'number');

  if (filas.length === 0) return { disponible: false, barras: [] };

  const mayor = Math.max(...filas.map((f) => f.n), 1);
  return {
    disponible: true,
    barras: filas.map((f) => ({ ...f, alto: Math.round((f.n / mayor) * 100) }))
  };
}

/**
 * El bloque «Órdenes de trabajo», de `indicadores_programacion`.
 *
 * Cada fila se muestra solo si su indicador llegó: una fila en 0 porque el
 * backend no la manda diría que no hay órdenes, que es otra cosa.
 *
 * @param {any} indicadores
 */
export function ordenesDeTrabajo(indicadores) {
  const prog = en(indicadores, ['programacion']);
  if (!prog) return { disponible: false, filas: [] };

  const fila = (clave, texto, tono) => {
    const v = valor(indicadores, ['programacion', clave]);
    return v == null ? null : { clave, texto, n: v, tono };
  };

  const filas = [
    fila('ordenes_sin_programar', 'Sin programar', 'alerta'),
    fila('ordenes_programadas', 'Programadas', 'teal'),
    fila('ordenes_abiertas', 'Abiertas', 'info'),
    fila('ordenes_total', 'Total del período', 'neutro')
  ].filter(Boolean);

  return { disponible: filas.length > 0, filas };
}

/**
 * La carga por técnico, de `/capacidad/jornada/`.
 *
 * El porcentaje es carga conocida sobre jornada. Cuando a alguien le faltan
 * duraciones, el riesgo del backend responde INDETERMINADO y aquí se respeta:
 * no se completa con un número ni se asume que está libre.
 *
 * @param {any[]} personas
 */
export function cargaPorTecnico(personas) {
  if (!Array.isArray(personas) || personas.length === 0) {
    return { disponible: false, filas: [] };
  }

  return {
    disponible: true,
    filas: personas.map((p) => {
      const jornada = p?.jornada?.minutos ?? null;
      const carga = p?.carga?.minutos_conocidos ?? null;
      const pct = jornada > 0 && carga != null ? Math.round((carga / jornada) * 100) : null;
      const riesgo = typeof p?.riesgo === 'string' ? p.riesgo : p?.riesgo?.estado;
      const faltantes = Array.isArray(p?.faltantes) ? p.faltantes.length : 0;

      let estado = 'Sin datos';
      let tono = 'neutro';
      if (riesgo === 'SOBRECARGA') {
        estado = 'Sobrecarga';
        tono = 'critico';
      } else if (riesgo === 'INDETERMINADO') {
        estado = 'Indeterminado';
        tono = 'neutro';
      } else if (pct != null) {
        if (pct >= 95) {
          estado = 'Al límite';
          tono = 'alerta';
        } else if (pct >= 60) {
          estado = 'Normal';
          tono = 'ok';
        } else {
          estado = 'Disponible';
          tono = 'info';
        }
      }

      return {
        nombre: p?.profile?.nombre ?? p?.profile?.email ?? 'Sin nombre',
        id: p?.profile?.id ?? null,
        pct,
        // Por encima del 100% la barra se llena y el número lo dice: cortarla
        // en 100 escondería justo el caso que importa.
        ancho: pct == null ? 0 : Math.min(pct, 100),
        carga,
        jornada,
        faltantes,
        estado,
        tono
      };
    })
  };
}

/**
 * El feed «Actividad reciente del Supervisor».
 *
 * Traduce el verbo crudo de `common.Activity` a algo legible y marca quién lo
 * hizo. `es_ia` viene del backend y significa que la fila no tiene usuario:
 * la escribió el Supervisor. No se deduce del texto.
 *
 * @param {any[]} eventos
 */
export function actividadReciente(eventos) {
  if (!Array.isArray(eventos) || eventos.length === 0) {
    return { disponible: false, filas: [] };
  }

  /** Los verbos que este módulo escribe. Uno que no esté viaja tal cual. */
  const VERBO = {
    CREATED: 'Propuesta generada',
    APPROVED: 'Propuesta aceptada',
    REJECTED: 'Propuesta rechazada',
    STATUS_CHANGED: 'Estado actualizado',
    UPDATED: 'Actualizada',
    DELETED: 'Cancelada'
  };

  return {
    disponible: true,
    filas: eventos.map((e) => ({
      id: e?.id ?? '',
      evento: VERBO[e?.accion] ?? e?.accion ?? '',
      detalle: e?.nombre || e?.descripcion || '',
      cuando: e?.cuando ?? null,
      quien: e?.quien ?? '',
      esIa: e?.es_ia === true
    }))
  };
}

/**
 * La celda de SLA de un hallazgo, a partir de lo que devuelve
 * `operaciones/sla.py`.
 *
 * LOS SEIS ESTADOS NO SE COLAPSAN EN DOS. «No hay plazo declarado» y «no se
 * pudo calcular» se verían igual como una celda vacía, y son cosas distintas:
 * la primera es una decisión del tipo de trabajo, la segunda es un dato que
 * falta. Y `NO_APLICA` quiere decir que la orden ya terminó -- llamarlo «a
 * tiempo» sería afirmar algo sobre un plazo que ya no corre.
 *
 * @param {string} estado
 * @param {number|null} minutos
 */
export function celdaDeSla(estado, minutos) {
  const dias = (m) => {
    if (m == null) return '';
    if (m < 60) return `${m} min`;
    if (m < 1440) return `${Math.round(m / 60)} h`;
    return `${Math.round(m / 1440)} d`;
  };

  switch (estado) {
    case 'VENCIDA':
      return {
        texto: 'Vencido',
        detalle: minutos != null ? `hace ${dias(minutos)}` : '',
        tono: 'critico'
      };
    case 'VENCE_PRONTO':
      return { texto: dias(minutos) || 'Por vencer', detalle: 'por vencer', tono: 'alerta' };
    case 'A_TIEMPO':
      return { texto: dias(minutos) || 'A tiempo', detalle: 'a tiempo', tono: 'ok' };
    case 'NO_APLICA':
      // La orden terminó. El plazo no corre; no es un incumplimiento ni un
      // cumplimiento.
      return { texto: 'N/A', detalle: 'la orden ya terminó', tono: 'neutro' };
    case 'SIN_PLAZO':
      return { texto: 'N/A', detalle: 'el tipo de trabajo no declara plazo', tono: 'neutro' };
    case 'DATOS_INSUFICIENTES':
      return { texto: '—', detalle: 'no se pudo determinar el plazo', tono: 'neutro' };
    default:
      // Sin estado: la propuesta no cuelga de una orden, que es donde vive el
      // plazo. Un caso o una actividad no tienen uno.
      return { texto: 'N/A', detalle: 'no cuelga de una orden de trabajo', tono: 'neutro' };
  }
}

/**
 * Lo que la pantalla NO puede mostrar todavía, con el motivo.
 *
 * Está en un solo lugar para que los bloques digan qué falta en vez de
 * quedar vacíos, y para que se borren de aquí el día que el dato exista.
 */
export const BLOQUES_SIN_DATO = {
  mapa: {
    titulo: 'Mapa de operación',
    motivo:
      'Las coordenadas existen en la orden (gps_lat/gps_lng), pero la propuesta solo ' +
      'apunta con origen_tipo + origen_id y no las trae.'
  },
};

/**
 * Las columnas de la tabla que el diseño pide y el backend no entrega.
 * Se declaran juntas para que la cabecera pueda marcarlas en vez de mostrar
 * una columna de rayas sin explicación.
 */
export const COLUMNAS_SIN_DATO = [];
