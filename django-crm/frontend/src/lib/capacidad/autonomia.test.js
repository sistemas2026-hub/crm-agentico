import { describe, it, expect } from 'vitest';
import { textoDeFalta, textoDeNoCandidata } from './autonomia.js';

/** La autonomía ganada, dicha para quien decide (31/10/2026). */

describe('textoDeFalta', () => {
  it('dice cuánto tiene y cuánto le falta', () => {
    expect(textoDeFalta({ condicion: 'minimo_revisadas', tiene: 12, necesita: 30 }))
      .toBe('Revisadas por una persona: 12 de 30.');
    expect(textoDeFalta({ condicion: 'tasa_minima_aprobacion', tiene: 0.925, necesita: 0.95 }))
      .toBe('Aprobadas sin cambios: 92.5%; hace falta 95%.');
  });

  it('0 de 0 no se dice como un porcentaje', () => {
    expect(textoDeFalta({ condicion: 'tasa_minima_aprobacion', tiene: null, necesita: 0.95 }))
      .toMatch(/Ninguna revisada todavía/);
  });

  it('una sola no confirmada o fallida se nombra en singular', () => {
    expect(textoDeFalta({ condicion: 'cero_no_confirmadas', tiene: 1, necesita: 0 })).toMatch(/^1 vez/);
    expect(textoDeFalta({ condicion: 'cero_fallidas', tiene: 2, necesita: 0 })).toMatch(/^2 ejecuciones fallaron/);
  });

  it('las condiciones de verificación se dicen en palabras', () => {
    expect(textoDeFalta({ condicion: 'minimo_confirmadas', tiene: 4, necesita: 20 })).toBe(
      'Reinicios con el efecto confirmado: 4 de 20.');
    expect(textoDeFalta({ condicion: 'proporcion_medida', tiene: 0.5, necesita: 0.8 })).toMatch(/50%/);
    expect(textoDeFalta({ condicion: 'cero_degradaciones', tiene: 1, necesita: 0 })).toMatch(/Perdió la autonomía/);
    expect(textoDeFalta({ condicion: 'tasa_minima_confirmacion', tiene: 0.8, necesita: 0.95 })).toMatch(/80%.*95%/);
  });

  it('una condición nueva se muestra con su código', () => {
    expect(textoDeFalta({ condicion: 'otra', tiene: 1, necesita: 2 })).toBe('otra: 1 (hace falta 2).');
  });
});

describe('textoDeNoCandidata', () => {
  it('traduce y junta', () => {
    expect(textoDeNoCandidata(['efecto_no_verificable', 'nuevo'])).toBe(
      'su efecto no se puede comprobar en código; nuevo'
    );
  });
});
