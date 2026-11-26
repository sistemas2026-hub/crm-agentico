import { describe, expect, it, vi } from 'vitest';

//  La traducción del formulario es pura; las llamadas al motor no se prueban
//  acá y su módulo carga el entorno del servidor.
vi.mock('./tenant.js', () => ({ destinoDelAsistente: vi.fn() }));
vi.mock('./motor-headers.js', () => ({ headersMotor: () => ({}) }));

import { cuerpoDeRangos } from './rangos-de-ip.js';

/** @param {Record<string, string>} campos */
function formulario(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return f;
}

describe('cuerpoDeRangos', () => {
  it('cada servidor con sus prefijos, separados por coma, espacio o renglón', () => {
    const c = cuerpoDeRangos(formulario({
      rango_zona_0: '20053', rango_nombre_0: 'CORTE 15 - SERVIDOR 1', rango_prefijos_0: '172.16.9., 172.16.10.',
      rango_zona_1: '20049', rango_nombre_1: 'CORTE 30 - SERVIDOR 1', rango_prefijos_1: '172.16.9.\n172.16.11.  172.16.12;'
    }));
    expect(c).toEqual([
      { zona_id: 20053, zona_nombre: 'CORTE 15 - SERVIDOR 1', prefijos: ['172.16.9.', '172.16.10.'] },
      { zona_id: 20049, zona_nombre: 'CORTE 30 - SERVIDOR 1', prefijos: ['172.16.9.', '172.16.11.', '172.16.12'] }
    ]);
  });

  it('un servidor sin rangos viaja con la lista vacía: es la forma de quitárselos', () => {
    const c = cuerpoDeRangos(formulario({ rango_zona_0: '32278', rango_nombre_0: 'SV', rango_prefijos_0: '  ' }),
      [{ zona_id: 32278, zona_nombre: 'SV', prefijos: ['172.16.40.'] }]);
    expect(c).toEqual([{ zona_id: 32278, zona_nombre: 'SV', prefijos: [] }]);
  });

  it('LO QUE NO SE VE NO SE BORRA: el rango guardado de otra zona se conserva', () => {
    const c = cuerpoDeRangos(formulario({ rango_zona_0: '20053', rango_prefijos_0: '172.16.9.' }), [
      { zona_id: 20053, zona_nombre: 'C15', prefijos: ['10.0.0.'] },
      { zona_id: 99999, zona_nombre: 'OTRA', prefijos: ['10.9.9.'] }
    ]);
    expect(c).toEqual([
      { zona_id: 20053, zona_nombre: '', prefijos: ['172.16.9.'] },
      { zona_id: 99999, zona_nombre: 'OTRA', prefijos: ['10.9.9.'] }
    ]);
  });

  it('se recorre por número de fila, aunque falten filas o vengan desordenadas', () => {
    const f = new FormData();
    f.set('rango_zona_3', '3');
    f.set('rango_prefijos_3', '10.0.3.');
    f.set('rango_zona_0', '1');
    f.set('rango_prefijos_0', '10.0.1.');
    expect(cuerpoDeRangos(f).map((p) => p.zona_id)).toEqual([1, 3]);
  });

  it('un número de zona con letras viaja como texto, para que el motor diga qué está mal', () => {
    expect(cuerpoDeRangos(formulario({ rango_zona_0: '20a', rango_prefijos_0: '' }))[0].zona_id).toBe('20a');
  });

  it('sin filas no hay rangos', () => {
    expect(cuerpoDeRangos(formulario({ nit: 'x' }))).toEqual([]);
  });
});
