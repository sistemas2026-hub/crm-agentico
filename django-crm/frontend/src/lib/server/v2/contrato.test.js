import { describe, expect, it, vi } from 'vitest';

//  La traducción del formulario es pura; la llamada al backend no se prueba
//  acá y su módulo carga el entorno del servidor.
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: vi.fn() }));

import { cuerpoDeContrato, FILAS_DE_SERVIDOR } from './contrato.js';

/** @param {Record<string, string>} campos */
function formulario(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return f;
}

describe('cuerpoDeContrato', () => {
  it('los servidores llegan con el número como entero', () => {
    const c = cuerpoDeContrato(formulario({
      servidor_id_0: '20053', servidor_nombre_0: 'CORTE 15 - SERVIDOR 1',
      servidor_id_1: ' 20061 ', servidor_nombre_1: 'CORTE 30 - SERVIDOR 2',
      nit: ' 900.000.000-0 ', texto_condiciones: 'Primera...'
    }));
    expect(c.servidores).toEqual([
      { id_zona: 20053, nombre: 'CORTE 15 - SERVIDOR 1' },
      { id_zona: 20061, nombre: 'CORTE 30 - SERVIDOR 2' }
    ]);
    expect(c.nit).toBe('900.000.000-0');
    expect(c.texto_condiciones).toBe('Primera...');
  });

  it('una fila vacía se ignora', () => {
    const c = cuerpoDeContrato(formulario({ servidor_id_3: '7', servidor_nombre_3: 'S3' }));
    expect(c.servidores).toEqual([{ id_zona: 7, nombre: 'S3' }]);
  });

  it('UNA FILA A MEDIAS SE MANDA, para que el backend diga qué falta', () => {
    //  Perderla en silencio dejaría a la empresa creyendo que cargó un
    //  servidor que no está.
    const c = cuerpoDeContrato(formulario({ servidor_id_0: '20053' }));
    expect(c.servidores).toEqual([{ id_zona: 20053, nombre: '' }]);
  });

  it('un número con letras viaja como texto y no se vuelve NaN', () => {
    const c = cuerpoDeContrato(formulario({ servidor_id_0: '20a', servidor_nombre_0: 'X' }));
    expect(c.servidores[0].id_zona).toBe('20a');
  });

  it('borrar todos los servidores manda la lista vacía', () => {
    expect(cuerpoDeContrato(formulario({})).servidores).toEqual([]);
    expect(FILAS_DE_SERVIDOR).toBeGreaterThanOrEqual(2);
  });
});
