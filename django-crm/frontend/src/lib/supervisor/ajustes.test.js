import { describe, expect, it } from 'vitest';

import { loQueLeFalta, tonoDeLaTarea } from './ajustes.js';

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
