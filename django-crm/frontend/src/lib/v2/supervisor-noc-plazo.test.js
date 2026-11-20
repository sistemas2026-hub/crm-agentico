import { describe, it, expect } from 'vitest';
import {
  grupoDePlazo,
  agruparPorPlazo,
  textoDePlazo,
  titularDelTablero,
  cuentaPorPlazo
} from './supervisor-noc-plazo.js';

const fila = (id, sla_estado, sla_minutos = null) => ({ id, sla_estado, sla_minutos });

describe('grupoDePlazo', () => {
  it('reparte los cuatro estados que calcula el backend', () => {
    expect(grupoDePlazo('VENCIDA')).toBe('vencido');
    expect(grupoDePlazo('VENCE_PRONTO')).toBe('pronto');
    expect(grupoDePlazo('A_TIEMPO')).toBe('plazo');
  });

  it('todo lo que no corre reloj cae en "sin plazo", nunca en "en plazo"', () => {
    //  Una orden terminada o un caso sin orden no está "a tiempo": no tiene
    //  reloj. Ponerlo en "En plazo" afirmaría un cumplimiento que nadie midió.
    for (const e of ['NO_APLICA', 'SIN_PLAZO', 'DATOS_INSUFICIENTES', null, undefined, 'OTRO']) {
      expect(grupoDePlazo(e)).toBe('sin');
    }
  });
});

describe('agruparPorPlazo', () => {
  it('ordena los grupos de lo más urgente a lo menos y omite los vacíos', () => {
    const g = agruparPorPlazo([fila('a', 'A_TIEMPO'), fila('b', 'VENCIDA'), fila('c', null)]);
    expect(g.map((x) => x.clave)).toEqual(['vencido', 'plazo', 'sin']);
  });

  it('dentro de cada grupo respeta el orden que ya trae la bandeja', () => {
    //  La bandeja llega ordenada por prioridad. Agrupar por plazo no debe
    //  reordenar por otra regla escondida.
    const g = agruparPorPlazo([fila('x', 'VENCIDA', 5), fila('y', 'VENCIDA', 500), fila('z', 'VENCIDA', 50)]);
    expect(g[0].filas.map((f) => f.id)).toEqual(['x', 'y', 'z']);
  });

  it('no pierde ni duplica filas', () => {
    const entrada = [fila('1', 'VENCIDA'), fila('2', 'VENCE_PRONTO'), fila('3', 'A_TIEMPO'), fila('4', 'NO_APLICA'), fila('5', 'VENCIDA')];
    const salida = agruparPorPlazo(entrada).flatMap((g) => g.filas.map((f) => f.id));
    expect(salida.sort()).toEqual(['1', '2', '3', '4', '5']);
  });

  it('una entrada que no es lista da cero grupos, no una excepción', () => {
    expect(agruparPorPlazo(null)).toEqual([]);
  });
});

describe('cuentaPorPlazo', () => {
  it('cuenta con la MISMA regla que agrupa', () => {
    const filas = [fila('1', 'VENCIDA'), fila('2', 'VENCIDA'), fila('3', 'VENCE_PRONTO'), fila('4', 'NO_APLICA')];
    const c = cuentaPorPlazo(filas);
    const g = Object.fromEntries(agruparPorPlazo(filas).map((x) => [x.clave, x.filas.length]));
    expect(c).toEqual({ vencido: 2, pronto: 1, plazo: 0, sin: 1 });
    expect(c.vencido).toBe(g.vencido);
    expect(c.pronto).toBe(g.pronto);
  });

  it('sin lista no inventa ceros: devuelve null', () => {
    expect(cuentaPorPlazo(null)).toBeNull();
  });
});

describe('textoDePlazo', () => {
  it('dice cuánto hace que venció, en horas y minutos', () => {
    const t = textoDePlazo('VENCIDA', 130);
    expect(t.texto).toBe('Venció hace 2 h 10 min');
    expect(t.tono).toBe('critico');
  });

  it('dice cuánto falta cuando vence pronto', () => {
    expect(textoDePlazo('VENCE_PRONTO', 45)).toMatchObject({ texto: 'Vence en 45 min', tono: 'alerta' });
  });

  it('en plazo, con días cuando corresponde', () => {
    expect(textoDePlazo('A_TIEMPO', 2 * 1440 + 180).texto).toBe('Quedan 2 d 3 h');
    expect(textoDePlazo('A_TIEMPO', 2 * 1440).texto).toBe('Quedan 2 d');
    expect(textoDePlazo('A_TIEMPO', 120).texto).toBe('Quedan 2 h');
  });

  it('sin minutos no inventa una duración', () => {
    expect(textoDePlazo('VENCIDA', null).texto).toBe('Vencido');
    expect(textoDePlazo('VENCE_PRONTO', undefined).texto).toBe('Vence pronto');
    expect(textoDePlazo('A_TIEMPO', null).texto).toBe('A tiempo');
  });

  it('sin plazo conserva el porqué que ya explicaba la tabla', () => {
    const t = textoDePlazo('NO_APLICA', null);
    expect(t.texto).toBe('Sin plazo');
    expect(t.detalle).toBe('la orden ya terminó');
    expect(t.tono).toBe('neutro');
  });
});

describe('titularDelTablero', () => {
  it('la frase dice cuántas esperan y cuántas vencieron', () => {
    const t = titularDelTablero({ pendientes: 12, vencido: 3, pronto: 4 });
    expect(t.principal).toBe('12 decisiones te esperan.');
    expect(t.alerta).toBe('3 ya vencieron el plazo.');
    expect(t.bajada).toBe('4 más vencen pronto.');
  });

  it('singular y plural', () => {
    const t = titularDelTablero({ pendientes: 1, vencido: 1, pronto: 1 });
    expect(t.principal).toBe('1 decisión te espera.');
    expect(t.alerta).toBe('1 ya venció el plazo.');
    expect(t.bajada).toBe('1 más vence pronto.');
  });

  it('sin vencidas no hay alerta, y la bajada lo dice', () => {
    const t = titularDelTablero({ pendientes: 5, vencido: 0, pronto: 0 });
    expect(t.alerta).toBeNull();
    expect(t.bajada).toBe('Ningún plazo vencido ni por vencer.');
  });

  it('cero pendientes es "nada espera", no "0 decisiones"', () => {
    const t = titularDelTablero({ pendientes: 0, vencido: 0, pronto: 0 });
    expect(t.principal).toBe('Nada espera tu decisión.');
    expect(t.alerta).toBeNull();
  });

  it('si la bandeja no se pudo leer, no afirma que no hay nada', () => {
    //  "Nada espera tu decisión" con la bandeja caída es la mentira más cara
    //  que puede decir esta pantalla.
    const t = titularDelTablero({ pendientes: null, vencido: null, pronto: null });
    expect(t.principal).toBe('No se pudo leer la bandeja.');
    expect(t.alerta).toBeNull();
    expect(t.bajada).toBeNull();
  });
});
