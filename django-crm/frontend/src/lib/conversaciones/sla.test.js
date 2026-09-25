import { describe, it, expect } from 'vitest';
import { plazoDeToma, textoDePlazo } from './sla.js';

/**
 * El plazo de toma decide de qué color se ve una fila y si alguien corre.
 * Es una cuenta, y una cuenta mal hecha no se ve mirando la pantalla: se ve
 * cuando un caso vencido aparece tranquilo, o cuando uno tranquilo aparece en
 * rojo y la alarma deja de significar algo.
 */

const AHORA = Date.parse('2026-09-21T20:00:00Z');
const haceMinutos = (/** @type {number} */ m) =>
  new Date(AHORA - m * 60000).toISOString();

/** Una escalada sin dueño, que es el único caso que el plazo mide. */
const esperando = (/** @type {number} */ min, extra = {}) => ({
  escalada_a_humano: true,
  asignada_a_usuario_id: null,
  estado: 'abierta',
  esperando_desde: haceMinutos(min),
  ...extra
});

describe('sin objetivo definido no se inventa ninguno', () => {
  it('0 minutos devuelve null, no un plazo por defecto', () => {
    expect(plazoDeToma(esperando(60), 0, AHORA)).toBeNull();
  });

  it('y un objetivo ausente tampoco', () => {
    expect(plazoDeToma(esperando(60), undefined, AHORA)).toBeNull();
    expect(plazoDeToma(esperando(60), null, AHORA)).toBeNull();
  });
});

describe('sólo mide lo que dice medir: escaladas sin dueño', () => {
  it('una que ya tiene dueño NO tiene plazo, aunque lleve horas', () => {
    // Está siendo atendida. Ponerle un reloj en rojo marcaría como
    // incumplimiento el trabajo normal.
    const mia = esperando(300, { asignada_a_usuario_id: 'alguien' });
    expect(plazoDeToma(mia, 15, AHORA)).toBeNull();
  });

  it('una que lleva la IA tampoco', () => {
    const deLaIA = esperando(300, { escalada_a_humano: false });
    expect(plazoDeToma(deLaIA, 15, AHORA)).toBeNull();
  });

  it('una cerrada tampoco', () => {
    expect(plazoDeToma(esperando(300, { estado: 'cerrada' }), 15, AHORA)).toBeNull();
  });

  it('sin fecha de espera no se puede afirmar nada', () => {
    const sinFecha = esperando(10);
    sinFecha.esperando_desde = null;
    expect(plazoDeToma(sinFecha, 15, AHORA)).toBeNull();
  });
});

describe('la cuenta', () => {
  it('dentro del plazo: restan los minutos que faltan', () => {
    const p = plazoDeToma(esperando(4), 15, AHORA);
    expect(p?.restanMinutos).toBe(11);
    expect(p?.vencido).toBe(false);
  });

  it('justo en el límite ya cuenta como vencido', () => {
    // A los 15 de un objetivo de 15 no quedan minutos: está incumplido.
    const p = plazoDeToma(esperando(15), 15, AHORA);
    expect(p?.restanMinutos).toBe(0);
    expect(p?.vencido).toBe(true);
  });

  it('pasado el plazo dice cuánto hace que venció', () => {
    const p = plazoDeToma(esperando(21), 15, AHORA);
    expect(p?.vencido).toBe(true);
    expect(p?.restanMinutos).toBe(-6);
  });
});

describe('«por vencer» es proporcional, no un número fijo', () => {
  it('con objetivo de 15 min avisa en el último tercio', () => {
    expect(plazoDeToma(esperando(10), 15, AHORA)?.porVencer).toBe(true);  // restan 5
    expect(plazoDeToma(esperando(4), 15, AHORA)?.porVencer).toBe(false);  // restan 11
  });

  it('con objetivo de 4 h el mismo "restan 5 min" también avisa', () => {
    // Y con restan 90 min no: en un plazo de 4 h, hora y media no es urgencia.
    expect(plazoDeToma(esperando(235), 240, AHORA)?.porVencer).toBe(true);
    expect(plazoDeToma(esperando(150), 240, AHORA)?.porVencer).toBe(false);
  });

  it('vencido no es «por vencer»: son dos estados distintos', () => {
    const p = plazoDeToma(esperando(30), 15, AHORA);
    expect(p?.vencido).toBe(true);
    expect(p?.porVencer).toBe(false);
  });
});

describe('cómo se escribe', () => {
  it('sin plazo no escribe nada', () => {
    expect(textoDePlazo(null)).toBe('');
  });

  it('dentro del plazo, los minutos pelados', () => {
    expect(textoDePlazo(plazoDeToma(esperando(4), 15, AHORA))).toBe('11m');
  });

  it('vencido lleva «+», nunca un signo menos', () => {
    // Un "-6m" se lee como un error de la aplicación, no como un
    // incumplimiento de seis minutos.
    expect(textoDePlazo(plazoDeToma(esperando(21), 15, AHORA))).toBe('+6m');
  });

  it('a partir de dos horas se escribe en horas', () => {
    expect(textoDePlazo(plazoDeToma(esperando(10), 240, AHORA))).toBe('4h');
  });
});
