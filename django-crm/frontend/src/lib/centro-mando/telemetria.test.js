import { describe, it, expect } from 'vitest';
import {
  CUBOS,
  normalizarSerie,
  hayActividad,
  rutaSparkline,
  rutaArea,
  proporcionCarga,
  cargaMaxima,
  arcoAnillo
} from './telemetria.js';

describe('la serie de actividad', () => {
  it('siempre trae los 15 cubos, aunque el motor mande menos', () => {
    expect(normalizarSerie([1, 2])).toHaveLength(CUBOS);
    expect(normalizarSerie([])).toHaveLength(CUBOS);
    expect(normalizarSerie(undefined)).toHaveLength(CUBOS);
  });

  it('una serie en cero no divide por cero: queda plana abajo', () => {
    const v = normalizarSerie(new Array(CUBOS).fill(0));
    expect(v.every((n) => n === 0)).toBe(true);
    expect(v.some(Number.isNaN)).toBe(false);
  });

  it('el pico llega a 1 y el resto queda proporcional', () => {
    const v = normalizarSerie([0, 5, 10, 5, 0]);
    expect(Math.max(...v)).toBe(1);
    expect(v[1]).toBeCloseTo(0.5);
  });

  it('se normaliza contra su propio maximo, no contra el de otro agente', () => {
    // Dos agentes con la misma FORMA se ven igual aunque uno mueva diez veces
    // mas volumen: comparar volumen es trabajo del anillo.
    const flojo = normalizarSerie([1, 2, 1]);
    const fuerte = normalizarSerie([10, 20, 10]);
    expect(flojo).toEqual(fuerte);
  });

  it('distingue una ventana vacia de una con actividad', () => {
    expect(hayActividad([0, 0, 0])).toBe(false);
    expect(hayActividad([0, 0, 1])).toBe(true);
  });

  it('ignora basura sin romperse', () => {
    const v = normalizarSerie([null, 'x', undefined, 4]);
    expect(v.some(Number.isNaN)).toBe(false);
    expect(Math.max(...v)).toBe(1);
  });
});

describe('la ruta que se dibuja', () => {
  it('empieza a la izquierda y termina a la derecha', () => {
    const d = rutaSparkline([1, 2, 3], 100, 20);
    expect(d.startsWith('M 0.0,')).toBe(true);
    expect(d).toContain('100.0,');
  });

  it('el valor mas alto toca el borde superior', () => {
    // alto - 1*alto = 0: arriba del todo.
    expect(rutaSparkline([0, 10], 10, 20)).toContain(',0.0');
  });

  it('el area cierra contra el suelo, para poder rellenarla', () => {
    const d = rutaArea([1, 2], 50, 10);
    expect(d.endsWith('L 50,10 L 0,10 Z')).toBe(true);
  });
});

describe('el anillo de carga', () => {
  it('se llena contra el agente mas cargado de la pantalla', () => {
    const agentes = [{ conversaciones: 31 }, { conversaciones: 16 }, { conversaciones: 0 }];
    const tope = cargaMaxima(agentes);
    expect(tope).toBe(31);
    expect(proporcionCarga(31, tope)).toBe(1);
    expect(proporcionCarga(16, tope)).toBeCloseTo(0.516, 2);
    expect(proporcionCarga(0, tope)).toBe(0);
  });

  it('con todos en cero nadie se llena', () => {
    const tope = cargaMaxima([{ conversaciones: 0 }, { conversaciones: 0 }]);
    expect(tope).toBe(0);
    expect(proporcionCarga(0, tope)).toBe(0);
  });

  it('nunca pasa de lleno aunque el dato venga raro', () => {
    expect(proporcionCarga(99, 10)).toBe(1);
    expect(proporcionCarga(-5, 10)).toBe(0);
  });

  it('el arco reparte la circunferencia entre pintado y resto', () => {
    const r = 20;
    const { pintado, resto, vuelta } = arcoAnillo(0.25, r);
    expect(vuelta).toBeCloseTo(2 * Math.PI * r);
    expect(pintado).toBeCloseTo(vuelta / 4);
    expect(pintado + resto).toBeCloseTo(vuelta);
  });

  it('sin agentes, la referencia es cero y no revienta', () => {
    expect(cargaMaxima([])).toBe(0);
    expect(cargaMaxima(undefined)).toBe(0);
  });
});
