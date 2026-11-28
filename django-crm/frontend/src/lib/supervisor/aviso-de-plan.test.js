import { describe, it, expect } from 'vitest';
import { avisoDelPlan } from './aviso-de-plan.js';

describe('cada acción de Planes semanales dice lo que hizo', () => {
  it('solo publicar dice «Plan publicado»', () => {
    expect(avisoDelPlan({ tipo: 'publicar' })).toContain('Plan publicado');
    for (const tipo of ['programar', 'reprogramar', 'secuencia', 'analizar', 'secuenciar']) {
      expect(avisoDelPlan({ tipo, orden: 1042, secuencia: 3 })).not.toContain('Plan publicado');
    }
  });

  it('programar y reprogramar nombran la orden', () => {
    expect(avisoDelPlan({ tipo: 'programar', orden: 1063 })).toContain('#1063');
    expect(avisoDelPlan({ tipo: 'reprogramar', orden: 1042 })).toContain('#1042');
  });

  it('secuencia 0 es «sin secuenciar»', () => {
    expect(avisoDelPlan({ tipo: 'secuencia', secuencia: '0' })).toContain('sin secuenciar');
    expect(avisoDelPlan({ tipo: 'secuencia', secuencia: '4' })).toContain('secuencia 4');
  });

  it('analizar cuenta las recomendaciones', () => {
    expect(avisoDelPlan({ tipo: 'analizar', asistente: { recomendaciones: [1, 2] } })).toContain('2 recomendaciones');
    expect(avisoDelPlan({ tipo: 'analizar', asistente: {} })).toContain('no encontró nada nuevo');
  });

  it('un tipo desconocido no inventa nada', () => {
    expect(avisoDelPlan({ tipo: 'otro' })).toBe('Hecho.');
    expect(avisoDelPlan(null)).toBe('Hecho.');
  });
});
