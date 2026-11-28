import { describe, expect, it, vi } from 'vitest';

//  La traducción del formulario es pura; la llamada al backend no se prueba acá.
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: vi.fn() }));

import { lineasDeMaterial } from './plantillas.js';

/** @param {Record<string, string>} campos */
function formulario(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return f;
}

//  EL MATERIAL QUE SE PRECARGA (26/11/2026)
describe('lineasDeMaterial', () => {
  it('cada fila con su cantidad, EN EL ORDEN de la pantalla, y vacía = la escribe el técnico', () => {
    const l = lineasDeMaterial(formulario({
      material_codigo_10: 'GRAPA', material_cantidad_10: '',
      material_codigo_2: 'SCAPC', material_cantidad_2: '2',
      material_codigo_3: ' ONU ', material_cantidad_3: '1',
      material_codigo_4: 'DROP', material_cantidad_4: '1,5',
      material_campo_4: ' Metros de fibra usados '
    }));
    expect(l).toEqual([
      { codigo: 'SCAPC', cantidad: 2, campo: '' },
      { codigo: 'ONU', cantidad: 1, campo: '' },
      { codigo: 'DROP', cantidad: 1.5, campo: 'Metros de fibra usados' },
      { codigo: 'GRAPA', cantidad: null, campo: '' }
    ]);
  });

  it('una fila sin material se ignora; una cantidad con letras viaja para que el backend lo diga', () => {
    const l = lineasDeMaterial(formulario({
      material_codigo_0: '', material_cantidad_0: '3',
      material_codigo_1: 'TENSOR', material_cantidad_1: 'dos'
    }));
    expect(l).toEqual([{ codigo: 'TENSOR', cantidad: 'dos', campo: '' }]);
  });

  it('sin filas, la lista vacía (vaciarla es una forma de guardarla)', () => {
    expect(lineasDeMaterial(formulario({ id: 'x' }))).toEqual([]);
  });
});
