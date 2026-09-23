import { describe, it, expect } from 'vitest';
import {
  kpisDelTablero,
  hallazgosPorTipo,
  estadoDeCasos,
  ordenesDeTrabajo,
  cargaPorTecnico,
  ticketsPorOrigen,
  actividadReciente
} from './supervisor-noc-tablero.js';

/**
 * Casi todas estas pruebas afirman sobre la MISMA distincion: un cero que el
 * backend dijo no es lo mismo que un hueco. Es la regla que la pantalla puede
 * romper sin que se note -- un `?? 0` de mas y un indicador caido se muestra
 * como "todo en orden".
 */

const conteo = (valor) => ({ estado: 'VALIDO', valor, unidad: 'conteo' });

const ARBOL = {
  supervisor: {
    senales_vigentes: conteo(99),
    senales_por_tipo: {
      orden_sin_programar: conteo(12),
      orden_sla_vencido: conteo(4),
      orden_sla_por_vencer: conteo(3),
      actividad_bloqueada: conteo(2),
      caso_desincronizado: conteo(7)
    }
  },
  casos: {
    por_estado: { abierto: conteo(40), en_proceso: conteo(20), cerrado: conteo(10) },
    por_origen: { wisphub: conteo(36), dexter: conteo(28) }
  },
  programacion: {
    ordenes_total: conteo(50),
    ordenes_abiertas: conteo(30),
    ordenes_programadas: conteo(18),
    ordenes_sin_programar: conteo(12)
  }
};

describe('kpisDelTablero', () => {
  it('devuelve los seis KPI del diseño, en orden', () => {
    const k = kpisDelTablero(ARBOL, []);
    expect(k.map((x) => x.clave)).toEqual([
      'hallazgos',
      'propuestas',
      'sla',
      'sin_programar',
      'bloqueados',
      'desinc'
    ]);
  });

  it('suma las dos señales de SLA en un solo KPI', () => {
    const k = kpisDelTablero(ARBOL, []);
    expect(k.find((x) => x.clave === 'sla').n).toBe(7); // 4 vencido + 3 por vencer
  });

  it('cuenta como pendientes solo las propuestas en estado propuesta', () => {
    const propuestas = [
      { estado: 'propuesta' },
      { estado: 'propuesta' },
      { estado: 'aceptada' },
      { estado: 'rechazada' }
    ];
    const k = kpisDelTablero(ARBOL, propuestas);
    expect(k.find((x) => x.clave === 'propuestas').n).toBe(2);
  });

  it('hallazgos vigentes y propuestas pendientes son numeros distintos', () => {
    // 99 señales vivas, 2 propuestas esperando. Que no coincidan es normal y
    // la pantalla los muestra como dos KPI, no como uno repetido.
    const k = kpisDelTablero(ARBOL, [{ estado: 'propuesta' }, { estado: 'propuesta' }]);
    expect(k.find((x) => x.clave === 'hallazgos').n).toBe(99);
    expect(k.find((x) => x.clave === 'propuestas').n).toBe(2);
  });

  it('con el arbol presente, un tipo de señal ausente vale cero', () => {
    // `senales_por_tipo` solo lista lo que ocurrio: sin la clave, no hubo
    // ninguna. Eso SI es un cero.
    const k = kpisDelTablero(ARBOL, []);
    expect(k.find((x) => x.clave === 'bloqueados').n).toBe(2); // solo actividad_bloqueada
  });

  it('sin el arbol, ningun KPI del supervisor inventa un cero', () => {
    const k = kpisDelTablero(null, []);
    for (const clave of ['hallazgos', 'sla', 'sin_programar', 'bloqueados', 'desinc']) {
      expect(k.find((x) => x.clave === clave).n).toBeNull();
    }
  });

  it('sin propuestas leidas, el KPI de pendientes queda en nulo y no en cero', () => {
    const k = kpisDelTablero(ARBOL, null);
    expect(k.find((x) => x.clave === 'propuestas').n).toBeNull();
  });

  it('una lista vacia de propuestas si es un cero', () => {
    const k = kpisDelTablero(ARBOL, []);
    expect(k.find((x) => x.clave === 'propuestas').n).toBe(0);
  });
});

describe('hallazgosPorTipo', () => {
  const muchas = (tipo, n) =>
    Array.from({ length: n }, () => ({ tipo_senal: tipo, tipo_senal_display: tipo.toUpperCase() }));

  it('reparte cien por ciento entre los tramos', () => {
    const d = hallazgosPorTipo([...muchas('a', 3), ...muchas('b', 1)]);
    expect(d.total).toBe(4);
    expect(d.tramos.reduce((t, x) => t + x.pct, 0)).toBe(100);
  });

  it('ordena de mayor a menor', () => {
    const d = hallazgosPorTipo([...muchas('a', 1), ...muchas('b', 5), ...muchas('c', 3)]);
    expect(d.tramos.map((t) => t.clave)).toEqual(['b', 'c', 'a']);
  });

  it('agrupa la cola en Otros y no pierde ninguna propuesta', () => {
    const p = [
      ...muchas('a', 8),
      ...muchas('b', 7),
      ...muchas('c', 6),
      ...muchas('d', 5),
      ...muchas('e', 4),
      ...muchas('f', 3),
      ...muchas('g', 2),
      ...muchas('h', 1)
    ];
    const d = hallazgosPorTipo(p);
    expect(d.tramos).toHaveLength(7);
    expect(d.tramos.at(-1)).toMatchObject({ clave: 'otros', n: 3 }); // g + h
    expect(d.tramos.reduce((t, x) => t + x.n, 0)).toBe(36);
  });

  it('los tramos se encadenan: cada uno arranca donde acabo el anterior', () => {
    const d = hallazgosPorTipo([...muchas('a', 1), ...muchas('b', 1)]);
    // El primero arranca en cero -- y `(-0).toFixed(2)` es "0.00", sin signo.
    expect(d.tramos[0].offset).toBe('0.00');
    expect(d.tramos[1].offset).toBe('-50.00');
  });

  it('usa la etiqueta legible cuando viene, y la clave cuando no', () => {
    const d = hallazgosPorTipo([
      { tipo_senal: 'orden_sin_programar', tipo_senal_display: 'Orden sin programación' },
      { tipo_senal: 'dato_incompleto' }
    ]);
    expect(d.tramos.map((t) => t.etiqueta).sort()).toEqual([
      'Orden sin programación',
      'dato_incompleto'
    ]);
  });

  it('sin propuestas no se dibuja el donut', () => {
    expect(hallazgosPorTipo([]).disponible).toBe(false);
    expect(hallazgosPorTipo(null).disponible).toBe(false);
  });
});

describe('estadoDeCasos', () => {
  it('escala las barras contra la mayor', () => {
    const d = estadoDeCasos(ARBOL);
    expect(d.disponible).toBe(true);
    expect(d.barras.find((b) => b.estado === 'abierto')).toMatchObject({ n: 40, alto: 100 });
    expect(d.barras.find((b) => b.estado === 'cerrado')).toMatchObject({ n: 10, alto: 25 });
  });

  it('acepta conteos crudos ademas de los que traen sobre', () => {
    const d = estadoDeCasos({ casos: { por_estado: { abierto: 2, cerrado: 1 } } });
    expect(d.barras.map((b) => b.n)).toEqual([2, 1]);
  });

  it('sin el bloque de casos no hay barras', () => {
    expect(estadoDeCasos(null).disponible).toBe(false);
    expect(estadoDeCasos({ casos: {} }).disponible).toBe(false);
  });

  it('todos los estados en cero no revientan la escala', () => {
    const d = estadoDeCasos({ casos: { por_estado: { abierto: conteo(0) } } });
    expect(d.barras[0].alto).toBe(0);
  });
});

describe('ordenesDeTrabajo', () => {
  it('trae las cuatro filas del bloque', () => {
    const d = ordenesDeTrabajo(ARBOL);
    expect(d.disponible).toBe(true);
    expect(d.filas.map((f) => f.n)).toEqual([12, 18, 30, 50]);
  });

  it('omite la fila cuyo indicador no llego, en vez de mostrarla en cero', () => {
    const d = ordenesDeTrabajo({ programacion: { ordenes_total: conteo(5) } });
    expect(d.filas.map((f) => f.clave)).toEqual(['ordenes_total']);
  });

  it('sin el bloque de programacion, el bloque entero se declara ausente', () => {
    expect(ordenesDeTrabajo(null).disponible).toBe(false);
    expect(ordenesDeTrabajo({}).disponible).toBe(false);
  });
});

describe('cargaPorTecnico', () => {
  const persona = (extra) => ({
    profile: { id: '1', nombre: 'Ana' },
    jornada: { minutos: 480 },
    carga: { minutos_conocidos: 240 },
    riesgo: 'SIN_SOBRECARGA',
    faltantes: [],
    ...extra
  });

  it('calcula el porcentaje como carga sobre jornada', () => {
    const d = cargaPorTecnico([persona()]);
    expect(d.filas[0].pct).toBe(50);
  });

  it('respeta INDETERMINADO en vez de llamarlo disponible', () => {
    // Con duraciones faltantes el backend no afirma nada sobre la carga. Que
    // el porcentaje calculado de bajo no autoriza a decir "disponible".
    const d = cargaPorTecnico([
      persona({ riesgo: 'INDETERMINADO', faltantes: [{ orden: 'x' }], carga: { minutos_conocidos: 60 } })
    ]);
    expect(d.filas[0].estado).toBe('Indeterminado');
    expect(d.filas[0].faltantes).toBe(1);
  });

  it('una sobrecarga manda sobre el porcentaje', () => {
    const d = cargaPorTecnico([persona({ riesgo: 'SOBRECARGA' })]);
    expect(d.filas[0].estado).toBe('Sobrecarga');
  });

  it('por encima del cien la barra se llena y el numero sigue diciendo la verdad', () => {
    const d = cargaPorTecnico([persona({ carga: { minutos_conocidos: 720 } })]);
    expect(d.filas[0].pct).toBe(150);
    expect(d.filas[0].ancho).toBe(100);
  });

  it('sin jornada no se divide por cero ni se inventa un porcentaje', () => {
    const d = cargaPorTecnico([persona({ jornada: { minutos: 0 } })]);
    expect(d.filas[0].pct).toBeNull();
    expect(d.filas[0].ancho).toBe(0);
    expect(d.filas[0].estado).toBe('Sin datos');
  });

  it('cae al correo cuando la persona no tiene nombre', () => {
    const d = cargaPorTecnico([persona({ profile: { id: '2', email: 'a@b.co' } })]);
    expect(d.filas[0].nombre).toBe('a@b.co');
  });

  it('sin personas el bloque se declara ausente', () => {
    expect(cargaPorTecnico([]).disponible).toBe(false);
    expect(cargaPorTecnico(null).disponible).toBe(false);
  });
});

describe('ticketsPorOrigen', () => {
  it('reparte el total entre los origenes que el campo distingue', () => {
    const d = ticketsPorOrigen(ARBOL);
    expect(d.disponible).toBe(true);
    expect(d.total).toBe(64);
    expect(d.tramos.map((t) => t.etiqueta)).toEqual(['WispHub', 'Dexter']);
    expect(d.tramos.map((t) => t.pct)).toEqual([56, 44]);
  });

  it('los tramos se encadenan', () => {
    const d = ticketsPorOrigen(ARBOL);
    expect(d.tramos[0].offset).toBe('0.00');
    expect(d.tramos[1].offset).toBe('-56.25');
  });

  it('un origen en cero no dibuja un tramo invisible', () => {
    const d = ticketsPorOrigen({ casos: { por_origen: { wisphub: conteo(5), dexter: conteo(0) } } });
    expect(d.tramos).toHaveLength(1);
    expect(d.total).toBe(5);
  });

  it('todo en cero es un bloque sin dato, no un donut vacio', () => {
    const d = ticketsPorOrigen({ casos: { por_origen: { wisphub: conteo(0) } } });
    expect(d.disponible).toBe(false);
  });

  it('sin el bloque de casos se declara ausente', () => {
    expect(ticketsPorOrigen(null).disponible).toBe(false);
    expect(ticketsPorOrigen({ casos: {} }).disponible).toBe(false);
  });

  it('una clave que no conoce viaja tal cual en vez de perderse', () => {
    const d = ticketsPorOrigen({ casos: { por_origen: { otro_isp: conteo(3) } } });
    expect(d.tramos[0].etiqueta).toBe('otro_isp');
  });
});

describe('actividadReciente', () => {
  const evento = (extra) => ({
    id: '1',
    accion: 'CREATED',
    nombre: 'Caso desincronizado CS-1842',
    cuando: '2026-09-23T10:45:00Z',
    quien: 'Supervisor NOC IA',
    es_ia: true,
    ...extra
  });

  it('traduce el verbo crudo de la auditoria', () => {
    const d = actividadReciente([evento(), evento({ id: '2', accion: 'APPROVED' })]);
    expect(d.filas.map((f) => f.evento)).toEqual(['Propuesta generada', 'Propuesta aceptada']);
  });

  it('un verbo que no conoce viaja tal cual y no se pierde la fila', () => {
    const d = actividadReciente([evento({ accion: 'REOPENED' })]);
    expect(d.filas[0].evento).toBe('REOPENED');
  });

  it('marca como IA solo lo que el backend marco, sin deducirlo del texto', () => {
    // `es_ia` sale de que la fila no tenga usuario. Un evento de una persona
    // cuyo texto mencione al Supervisor NO es un evento de la IA.
    const d = actividadReciente([
      evento({ id: '1', es_ia: true }),
      evento({ id: '2', es_ia: false, quien: 'ana@rapilink.co', nombre: 'Revisó una propuesta del Supervisor' })
    ]);
    expect(d.filas.map((f) => f.esIa)).toEqual([true, false]);
  });

  it('cae a la descripcion cuando el evento no tiene nombre', () => {
    const d = actividadReciente([evento({ nombre: '', descripcion: 'Sin nombre de entidad' })]);
    expect(d.filas[0].detalle).toBe('Sin nombre de entidad');
  });

  it('un feed vacio se declara ausente', () => {
    expect(actividadReciente([]).disponible).toBe(false);
    expect(actividadReciente(null).disponible).toBe(false);
  });
});
