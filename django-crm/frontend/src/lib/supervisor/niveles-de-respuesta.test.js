import { describe, expect, it } from 'vitest';

import { quienLoDecidio, textoDelPlazo } from './niveles-de-respuesta.js';

describe('el plazo de un nivel', () => {
  it('cero es el mismo día', () => {
    expect(textoDelPlazo(0)).toBe('mismo día');
  });
  it('uno y varios', () => {
    expect(textoDelPlazo(1)).toBe('1 día');
    expect(textoDelPlazo(5)).toBe('5 días');
  });
});

describe('quién decidió el nivel de un asunto', () => {
  const fecha = (/** @type {string} */ iso) => iso.slice(0, 10);

  it('el Supervisor dice por qué', () => {
    expect(quienLoDecidio({ por: 'supervisor', motivo: '4 de 5 tickets fueron falla de servicio' }))
      .toBe('Supervisor · 4 de 5 tickets fueron falla de servicio');
  });
  it('una persona, con su nombre y cuándo, y que ya no se toca', () => {
    expect(quienLoDecidio({ por: 'persona', decidido_por: 'Ana', decidido_en: '2026-10-24T15:00:00Z' }, fecha))
      .toBe('Ana, 2026-10-24 · el Supervisor no lo vuelve a tocar');
  });
  it('un asunto que nadie ubicó lo dice', () => {
    expect(quienLoDecidio({ por: null, nivel: null })).toBe('Sin nivel todavía');
  });
  it('una persona sin nombre no se muestra vacía', () => {
    expect(quienLoDecidio({ por: 'persona', decidido_por: '' }))
      .toBe('Una persona · el Supervisor no lo vuelve a tocar');
  });
});
