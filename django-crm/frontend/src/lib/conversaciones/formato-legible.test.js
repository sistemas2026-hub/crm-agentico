/**
 * Cómo se leen los datos crudos del ISP y del canal (04/11/2026).
 *
 * Lo que protege: que el formato no invente. Cada función tiene una prueba
 * negativa --lo que no reconoce vuelve tal cual-- porque un dato «corregido» a
 * ciegas se ve bien y está mal, y ése es el defecto que no se ve en pantalla.
 */
import { describe, it, expect } from 'vitest';
import { telefonoLegible, fechaLegible, diasHasta, montoLegible } from './formato.js';

describe('el teléfono del canal', () => {
  it('agrupa el número colombiano', () => {
    expect(telefonoLegible('573023608750')).toBe('+57 302 360 8750');
    expect(telefonoLegible('+573243022467')).toBe('+57 324 302 2467');
  });

  it('otro país va entero con su +, sin agrupar a ciegas', () => {
    expect(telefonoLegible('5215512345678')).toBe('+5215512345678');
  });

  it('diez cifras sin indicativo NO reciben un + inventado', () => {
    expect(telefonoLegible('3001234567')).toBe('300 123 4567');
    expect(telefonoLegible('3001234567')).not.toMatch(/^\+/);
    expect(telefonoLegible('12345678')).toBe('12345678');
  });

  it('lo que no es un número vuelve sin tocar', () => {
    expect(telefonoLegible('MARIO SABANAGRANDE')).toBe('MARIO SABANAGRANDE');
    expect(telefonoLegible('CO.1360399936298471')).toBe('CO.1360399936298471');
    expect(telefonoLegible('1234')).toBe('1234');
    expect(telefonoLegible(null)).toBe('');
  });
});

describe('la fecha del ISP', () => {
  it('un solo formato, sin segundos', () => {
    expect(fechaLegible('30/05/2025 10:58:00')).toBe('30/05/2025 10:58');
    expect(fechaLegible('6/11/2026')).toBe('06/11/2026');
    expect(fechaLegible('2026-11-06')).toBe('06/11/2026');
  });

  it('día/mes, nunca mes/día', () => {
    expect(fechaLegible('6/11/2026')).not.toBe('11/06/2026');
  });

  it('lo que no reconoce vuelve tal cual', () => {
    expect(fechaLegible('el próximo lunes')).toBe('el próximo lunes');
    expect(fechaLegible(undefined)).toBe('');
  });
});

describe('cuánto falta para una fecha', () => {
  const hoy = new Date(2026, 10, 4, 15, 30); // 04/11/2026 a media tarde

  it('cuenta días de calendario, no horas', () => {
    expect(diasHasta('6/11/2026', hoy)).toBe(2);
    expect(diasHasta('04/11/2026', hoy)).toBe(0);
    expect(diasHasta('2026-11-01', hoy)).toBe(-3);
  });

  it('sin fecha reconocible no hay cuenta', () => {
    expect(diasHasta('sin corte', hoy)).toBeNull();
    expect(diasHasta(null, hoy)).toBeNull();
  });
});

describe('el saldo', () => {
  it('sin decimales vacíos y con separador de miles', () => {
    expect(montoLegible('0.00')).toBe('0');
    expect(montoLegible('45000.00')).toBe('45.000');
  });

  it('los decimales que no son cero se muestran', () => {
    expect(montoLegible('1234.5')).toBe('1.234,50');
  });

  it('no inventa moneda', () => {
    expect(montoLegible('45000')).not.toMatch(/\$|COP|USD/);
  });

  it('lo que no es un número vuelve tal cual', () => {
    expect(montoLegible('Pagadas')).toBe('Pagadas');
    expect(montoLegible('')).toBe('');
  });
});
