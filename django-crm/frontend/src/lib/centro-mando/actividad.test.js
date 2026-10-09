import { describe, it, expect } from 'vitest';
import { eventosNuevos, animacionDe, repartir, MAXIMO_POR_LECTURA } from './actividad.js';

const ev = (tipo, extra = {}) => ({
  en: '2026-09-25T02:00:00.000Z', agente: 'soporte', tipo, ...extra
});

describe('que eventos son nuevos', () => {
  it('sin lectura previa, todos', () => {
    expect(eventosNuevos([], [ev('consulta'), ev('escalada')])).toHaveLength(2);
  });

  it('los ya vistos no se repiten', () => {
    // El payload se serializa de nuevo en cada sondeo: los objetos nunca son
    // los mismos aunque describan el mismo hecho. Sin comparar por clave,
    // cada lectura reanimaria los veinte del ticker.
    const antes = [ev('consulta', { herramienta: 'consultar_olt' })];
    const ahora = [
      { ...ev('consulta', { herramienta: 'consultar_olt' }) },  // el MISMO hecho, otro objeto
      ev('escalada', { motivo: 'reclamo' })
    ];
    const nuevos = eventosNuevos(antes, ahora);
    expect(nuevos).toHaveLength(1);
    expect(nuevos[0].tipo).toBe('escalada');
  });

  it('dos eventos del mismo agente en distinto instante son distintos', () => {
    const a = [{ en: 'T1', agente: 'soporte', tipo: 'consulta', herramienta: 'x' }];
    const b = [
      { en: 'T1', agente: 'soporte', tipo: 'consulta', herramienta: 'x' },
      { en: 'T2', agente: 'soporte', tipo: 'consulta', herramienta: 'x' }
    ];
    expect(eventosNuevos(a, b)).toHaveLength(1);
  });

  it('aguanta listas vacias o ausentes', () => {
    expect(eventosNuevos(null, null)).toEqual([]);
    expect(eventosNuevos(undefined, [])).toEqual([]);
  });
});

describe('que se anima y que no', () => {
  it('una escalada se ve salir', () => {
    expect(animacionDe(ev('escalada')).forma).toBe('sale');
  });

  it('un fallo de herramienta se ve', () => {
    expect(animacionDe(ev('herramienta_fallida')).forma).toBe('falla');
  });

  it('un tipo desconocido NO se anima', () => {
    // Si todo se mueve, el movimiento deja de ser una senal.
    expect(animacionDe(ev('algo_que_no_existe'))).toBeNull();
    expect(animacionDe(null)).toBeNull();
    expect(animacionDe({})).toBeNull();
  });
});

describe('el reparto a lo largo de la ventana', () => {
  it('sin eventos no programa nada', () => {
    expect(repartir([]).programadas).toEqual([]);
    expect(repartir(null).programadas).toEqual([]);
  });

  it('escalona en vez de disparar todo de golpe', () => {
    // Es la razon de ser de este modulo: doce segundos quietos y medio
    // segundo con ocho cosas moviendose no se puede leer.
    const muchos = Array.from({ length: 5 }, (_, i) => ev('consulta', { en: `T${i}` }));
    const { programadas } = repartir(muchos, { ventanaMs: 12000 });
    const retrasos = programadas.map((p) => p.retraso);
    expect(retrasos[0]).toBe(0);
    expect(new Set(retrasos).size).toBe(retrasos.length);   // todos distintos
    expect(retrasos).toEqual([...retrasos].sort((a, b) => a - b));
  });

  it('la ultima animacion TERMINA antes de la proxima lectura', () => {
    // Si no, el repintado la corta a la mitad.
    const muchos = Array.from({ length: 6 }, (_, i) => ev('escalada', { en: `T${i}` }));
    const { programadas } = repartir(muchos, { ventanaMs: 12000 });
    for (const p of programadas) {
      expect(p.retraso + p.duracion).toBeLessThanOrEqual(12000);
    }
  });

  it('lo que mas dice va primero', () => {
    const mezcla = [
      ev('consulta', { en: 'T1' }),
      ev('escalada', { en: 'T2' }),
      ev('consulta', { en: 'T3' })
    ];
    const { programadas } = repartir(mezcla);
    expect(programadas[0].evento.tipo).toBe('escalada');
  });

  it('con demasiados, descarta los que menos dicen y lo DICE', () => {
    const muchos = [
      ...Array.from({ length: 20 }, (_, i) => ev('consulta', { en: `C${i}` })),
      ev('escalada', { en: 'E1' })
    ];
    const { programadas, descartados } = repartir(muchos, { maximo: 3 });
    expect(programadas).toHaveLength(3);
    expect(descartados).toBe(18);
    // la escalada no se pierde aunque venga ultima en la lista
    expect(programadas.some((p) => p.evento.tipo === 'escalada')).toBe(true);
  });

  it('un solo evento no necesita reparto', () => {
    const { programadas } = repartir([ev('escalada')]);
    expect(programadas).toHaveLength(1);
    expect(programadas[0].retraso).toBe(0);
  });

  it('el tope por lectura es el declarado', () => {
    const muchos = Array.from({ length: 50 }, (_, i) => ev('consulta', { en: `T${i}` }));
    expect(repartir(muchos).programadas.length).toBe(MAXIMO_POR_LECTURA);
  });
});
