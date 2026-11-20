/**
 * El aviso de la fecha de corte y el teléfono del canal (04/11/2026).
 *
 * Lo que protege: que el aviso diga el día correcto en los bordes (hoy,
 * mañana, el último día que se avisa, el primero que ya no) y que no aparezca
 * cuando la fecha no se reconoce -- un «vence hoy» sobre una fecha mal leída
 * es una promesa falsa al cliente.
 */
import { describe, it, expect } from 'vitest';
import { avisoDeCorte, telefonoDelCanal, DIAS_DE_AVISO_DE_CORTE } from './ficha-cliente.js';

// Mediodía, para que ningún huso corra la fecha de calendario.
const HOY = new Date(2026, 10, 4, 12, 0, 0); // 04/11/2026

describe('avisoDeCorte', () => {
  it('hoy, mañana y en N días hasta el borde', () => {
    expect(avisoDeCorte('4/11/2026', HOY)).toBe('hoy');
    expect(avisoDeCorte('05/11/2026', HOY)).toBe('mañana');
    expect(avisoDeCorte('06/11/2026 10:58:00', HOY)).toBe('en 2 días');
    expect(avisoDeCorte('2026-11-07', HOY)).toBe('en 3 días');
  });

  it('más allá del borde no avisa', () => {
    expect(DIAS_DE_AVISO_DE_CORTE).toBe(3);
    expect(avisoDeCorte('08/11/2026', HOY)).toBeNull();
    expect(avisoDeCorte('30/12/2026', HOY)).toBeNull();
  });

  it('si ya pasó, dice hace cuánto, en singular y en plural', () => {
    expect(avisoDeCorte('03/11/2026', HOY)).toBe('venció hace 1 día');
    expect(avisoDeCorte('25/10/2026', HOY)).toBe('venció hace 10 días');
  });

  it('día/mes, nunca mes/día', () => {
    // 11/04 leído como mes/día sería «hoy»; es el 11 de abril.
    expect(avisoDeCorte('11/04/2026', HOY)).toBe('venció hace 207 días');
  });

  it('una fecha que no se reconoce no inventa aviso', () => {
    for (const v of [null, undefined, '', 'sin fecha', '2026/11/04', 'mañana']) {
      expect(avisoDeCorte(v, HOY)).toBeNull();
    }
  });
});

describe('telefonoDelCanal', () => {
  it('diez cifras locales se agrupan sin inventar un +', () => {
    expect(telefonoDelCanal('3001234567')).toBe('300 123 4567');
  });

  it('el plan colombiano con 57 pasa por telefonoLegible', () => {
    expect(telefonoDelCanal('573001234567')).toBe('+57 300 123 4567');
    expect(telefonoDelCanal('+573001234567')).toBe('+57 300 123 4567');
  });

  it('lo que no es un número vuelve tal cual', () => {
    expect(telefonoDelCanal('CO.1360399936298471')).toBe('CO.1360399936298471');
    expect(telefonoDelCanal('')).toBe('');
    expect(telefonoDelCanal(null)).toBe('');
  });
});
