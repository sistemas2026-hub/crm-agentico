import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api-helpers.js', () => ({ apiRequest: vi.fn() }));

import { puntosDeTvDel } from './plantillas.js';

/** @param {Record<string, string>} campos */
function formulario(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return f;
}

//  LOS PUNTOS DE TV (26/11/2026)
describe('puntosDeTvDel', () => {
  it('todo el formulario, con los spliters en orden y sin las filas vacías', () => {
    expect(puntosDeTvDel(formulario({
      tv_activo: 'on', tv_conector: ' CONCOAX ', tv_por_punto: '2', tv_entrada: '2',
      tv_maximo: '5', tv_cable: 'RG6',
      tv_spliter_codigo_3: 'SPL4', tv_spliter_salidas_3: '4',
      tv_spliter_codigo_0: 'SPL2', tv_spliter_salidas_0: '2',
      tv_spliter_codigo_1: '', tv_spliter_salidas_1: '3'
    }))).toEqual({
      activo: true, conector: 'CONCOAX', conectores_por_punto: '2', conectores_de_entrada: '2',
      maximo_de_puntos: '5', cable: 'RG6',
      spliters: [{ codigo: 'SPL2', salidas: '2' }, { codigo: 'SPL4', salidas: '4' }]
    });
  });

  it('LA CASILLA DESMARCADA VIAJA COMO false: si no, no habría cómo apagarlo', () => {
    expect(puntosDeTvDel(formulario({ tv_conector: 'CONCOAX' })).activo).toBe(false);
  });
});
