import { describe, it, expect } from 'vitest';
import { fechaSugerida } from './despacho-sugerencias.js';

//  Las fechas se arman con el constructor LOCAL, igual que la función: la
//  prueba no depende de la zona horaria de la máquina que la corre.
const hoy = new Date(2026, 9, 19, 18, 30); // 19/10/2026 18:30

describe('«para cuándo»: creación del ticket + plazo de la plantilla', () => {
  it('suma el plazo al día en que se creó', () => {
    const creado = new Date(2026, 9, 18, 9, 0).toISOString();
    expect(fechaSugerida(creado, 3, hoy)).toBe('2026-10-21');
  });

  it('si ese día ya pasó, propone hoy y no una fecha vencida', () => {
    const creado = new Date(2026, 9, 10, 9, 0).toISOString();
    expect(fechaSugerida(creado, 2, hoy)).toBe('2026-10-19');
  });

  it('plazo 0 es el mismo día de creación (o hoy, si ya pasó)', () => {
    const creadoHoy = new Date(2026, 9, 19, 8, 0).toISOString();
    expect(fechaSugerida(creadoHoy, 0, hoy)).toBe('2026-10-19');
  });

  it('cruza el fin de mes', () => {
    const creado = new Date(2026, 9, 30, 9, 0).toISOString();
    expect(fechaSugerida(creado, 3, new Date(2026, 9, 30))).toBe('2026-11-02');
  });

  it('sin plazo declarado o sin creación no inventa una fecha', () => {
    const creado = new Date(2026, 9, 18).toISOString();
    expect(fechaSugerida(creado, null, hoy)).toBe('');
    expect(fechaSugerida(creado, undefined, hoy)).toBe('');
    expect(fechaSugerida(null, 3, hoy)).toBe('');
    expect(fechaSugerida('no es fecha', 3, hoy)).toBe('');
  });
});
