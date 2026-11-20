/**
 * EL RELOJ DE LA PRIMERA RESPUESTA. Se siembra siempre el vencimiento del
 * SERVIDOR distinto de `opened_at + horas`: si la funcion recalculara con las
 * horas, estas pruebas lo verian (el calendario laboral y la pausa corren el
 * vencimiento, y la pantalla no puede dar una segunda respuesta).
 */
import { describe, expect, it } from 'vitest';
import { duracionCorta, plazoPrimeraRespuesta } from './plazo-primera-respuesta.js';

const H = 3600e3;
const ABIERTO = Date.parse('2026-10-24T13:00:00Z');
const base = {
  opened_at: new Date(ABIERTO).toISOString(),
  first_response_hours: 4,
  // 10 h despues, no 4: el calendario laboral lo corrio. Es el que manda.
  first_response_deadline: new Date(ABIERTO + 10 * H).toISOString(),
  first_response_at: null,
  first_response_breached: false,
  paused_at: null,
  is_open: true
};

describe('plazoPrimeraRespuesta', () => {
  it('corriendo al 20 %: indigo, y el vencimiento es el del servidor', () => {
    const p = plazoPrimeraRespuesta(base, ABIERTO + 2 * H);
    expect(p.estado).toBe('corriendo');
    expect(p.pct).toBe(20);
    expect(p.tono).toBe('ember');
    expect(p.texto).toBe('Vence en 8 h');
    expect(p.plazo).toBe('Plazo de 4 h');
  });

  it('desde el 75 % es clay', () => {
    const p = plazoPrimeraRespuesta(base, ABIERTO + 8 * H);
    expect(p.pct).toBe(80);
    expect(p.tono).toBe('clay');
  });

  it('vencida: rust y cuanto se paso', () => {
    // A las 5 h ya pasaron las 4 h del plazo, pero NO el vencimiento real.
    expect(plazoPrimeraRespuesta(base, ABIERTO + 5 * H).estado).toBe('corriendo');
    const p = plazoPrimeraRespuesta(base, ABIERTO + 12 * H);
    expect(p.estado).toBe('vencida');
    expect(p.tono).toBe('rust');
    expect(p.pct).toBe(100);
    expect(p.texto).toBe('Primera respuesta vencida hace 2 h');
  });

  it('respondida: moss y cuanto tardo', () => {
    const p = plazoPrimeraRespuesta(
      { ...base, first_response_at: new Date(ABIERTO + 45 * 6e4).toISOString() },
      ABIERTO + 20 * H
    );
    expect(p.estado).toBe('respondida');
    expect(p.tono).toBe('moss');
    expect(p.texto).toBe('Respondida a los 45 min');
  });

  it('respondida tarde lo dice, sin dejar de ser respondida', () => {
    const p = plazoPrimeraRespuesta({
      ...base,
      first_response_at: new Date(ABIERTO + 11 * H).toISOString(),
      first_response_breached: true
    });
    expect(p.texto).toBe('Respondida a los 11 h, fuera de plazo');
  });

  it('en pausa no da un "vence en" que se mueve solo', () => {
    const p = plazoPrimeraRespuesta({ ...base, paused_at: new Date(ABIERTO + H).toISOString() }, ABIERTO + 12 * H);
    expect(p.estado).toBe('pausada');
    expect(p.texto).not.toMatch(/Vence|vencida/);
  });

  it('sin objetivo y cerrado sin respuesta', () => {
    expect(plazoPrimeraRespuesta({ ...base, first_response_deadline: null, first_response_hours: null }).estado)
      .toBe('sin_objetivo');
    expect(plazoPrimeraRespuesta({ ...base, is_open: false }).estado).toBe('cerrada_sin_respuesta');
  });
});

describe('duracionCorta', () => {
  it('minutos, horas y dias', () => {
    expect(duracionCorta(0.2)).toBe('menos de 1 min');
    expect(duracionCorta(12)).toBe('12 min');
    expect(duracionCorta(150)).toBe('3 h');
    expect(duracionCorta(1440)).toBe('1 día');
    expect(duracionCorta(3 * 1440)).toBe('3 días');
  });
});
