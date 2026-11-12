import { describe, expect, it } from 'vitest';

import { comoLlego, loQueLeFalta, separarPorCritica, tonoDeLaTarea } from './ajustes.js';

describe('lo no crítico nace delegado (12/11/2026)', () => {
  it('una delegada por defecto no se le atribuye a nadie', () => {
    expect(comoLlego({ delegada: true, por_omision: true, delegada_por: 'Ana' })).toBe(
      'La hace sola desde el primer día: nadie la cambió.'
    );
  });
  it('una delegada por una persona la nombra, y una quitada también', () => {
    expect(comoLlego({ delegada: true, por_omision: false, delegada_por: 'Ana' })).toBe('La delegó Ana');
    expect(comoLlego({ delegada: false, quitada_por: 'Luis' })).toBe('La quitó Luis');
  });
  it('separa lo que hace solo de lo crítico, y sin el dato cuenta como crítica', () => {
    const g = separarPorCritica([
      { clave: 'a', critica: false },
      { clave: 'b', critica: true },
      { clave: 'c' }
    ]);
    expect(g.solas.map((t) => t.clave)).toEqual(['a']);
    expect(g.criticas.map((t) => t.clave)).toEqual(['b', 'c']);
  });
});

/** Una tarea que no le falta nada. @param {any} [cambios] */
const tarea = (cambios = {}) => ({
  delegada: true,
  exige_nivel: 3,
  nivel_alcanza: true,
  la_despierta_algo: { si: true, por_que: '' },
  requiere: [],
  ...cambios
});

describe('lo que le falta a una tarea para actuar', () => {
  it('nada, si el nivel alcanza, algo la despierta y lo que requiere está', () => {
    expect(loQueLeFalta(tarea(), 3)).toEqual([]);
  });

  it('el nivel, con el que exige y el que aplica', () => {
    const f = loQueLeFalta(tarea({ nivel_alcanza: false }), 1);
    expect(f).toHaveLength(1);
    expect(f[0]).toContain('3');
    expect(f[0]).toContain('1');
  });

  it('que nada la despierte, con el porqué del backend', () => {
    const f = loQueLeFalta(
      tarea({ la_despierta_algo: { si: false, por_que: 'nada la va a correr sola todavía' } }),
      3
    );
    expect(f).toEqual(['Nada la va a correr sola todavía.']);
  });

  it('la tarea en la que se apoya, solo si no está delegada', () => {
    const r = [{ nombre: 'Pasar casos a Despacho', delegada: false }];
    expect(loQueLeFalta(tarea({ requiere: r }), 3)).toHaveLength(1);
    const ok = [{ nombre: 'Pasar casos a Despacho', delegada: true }];
    expect(loQueLeFalta(tarea({ requiere: ok }), 3)).toEqual([]);
  });

  it('los tres juntos, sin que uno tape al otro', () => {
    const f = loQueLeFalta(
      tarea({
        nivel_alcanza: false,
        la_despierta_algo: { si: false, por_que: 'falta el ciclo' },
        requiere: [{ nombre: 'Otra', delegada: false }]
      }),
      0
    );
    expect(f).toHaveLength(3);
  });
});

describe('el punto de color de la fila', () => {
  it('apagada si no está delegada, aunque no le falte nada', () => {
    expect(tonoDeLaTarea(tarea({ delegada: false }), 3)).toBe('apagada');
  });
  it('andando si está delegada y no le falta nada', () => {
    expect(tonoDeLaTarea(tarea(), 3)).toBe('andando');
  });
  it('trabada si está delegada y algo le falta: delegada no es andando', () => {
    expect(tonoDeLaTarea(tarea({ nivel_alcanza: false }), 1)).toBe('trabada');
  });
});
