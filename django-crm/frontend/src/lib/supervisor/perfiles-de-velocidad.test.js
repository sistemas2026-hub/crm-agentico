import { describe, expect, it } from 'vitest';

/**
 * EL ANCHO DE BANDA DE CADA PLAN (27/11/2026): qué muestra la tabla. Lo
 * guardado manda; lo sugerido llena lo que falta y se marca; un plan guardado
 * que ya no se vende no se pierde de vista.
 */
import { filasDePerfiles } from './perfiles-de-velocidad.js';

/** @type {any} */
const DEL_MOTOR = {
  disponible: true,
  error: '',
  perfiles: { bajada: [], subida: [] },
  planes: [
    { nombre: 'PLAN FAMILIA', bajada: '200M', subida: '100M',
      sugerido: { bajada: 'PLAN_200MB_SV', subida: 'PLAN_100MB' } },
    { nombre: 'PLAN ELITE', bajada: '700M', subida: '350M',
      sugerido: { bajada: 'PLAN_700MB', subida: 'PLAN_1000MB' } },
    { nombre: 'PLAN NUEVO', bajada: '', subida: '', sugerido: { bajada: '', subida: '' } }
  ]
};

describe('filasDePerfiles', () => {
  it('sin nada guardado, cada plan sale con lo sugerido y marcado', () => {
    const f = filasDePerfiles(DEL_MOTOR, []);
    expect(f[0]).toEqual({ plan: 'PLAN FAMILIA', velocidad: '200M / 100M', bajada: 'PLAN_200MB_SV',
                           subida: 'PLAN_100MB', sugerido: true, seVende: true,
                           sugeridos: { bajada: 'PLAN_200MB_SV', subida: 'PLAN_100MB' },
                           kbps: { bajada: 200000, subida: 100000 } });
    expect(f[2]).toMatchObject({ plan: 'PLAN NUEVO', velocidad: '', bajada: '', subida: '', sugerido: false, seVende: true,
                                 kbps: { bajada: null, subida: null } });
  });

  it('LO GUARDADO MANDA sobre lo sugerido, aunque el nombre venga con otros espacios', () => {
    const f = filasDePerfiles(DEL_MOTOR, [{ plan: 'plan  elite', bajada: 'PLAN_1000MB', subida: 'PLAN_1000MB' }]);
    expect(f[1]).toMatchObject({ plan: 'PLAN ELITE', bajada: 'PLAN_1000MB', subida: 'PLAN_1000MB', sugerido: false });
  });

  it('un plan guardado que ya no se vende sale al final, para no borrarlo sin verlo', () => {
    const f = filasDePerfiles(DEL_MOTOR, [{ plan: 'PLAN VIEJO', bajada: 'PLAN_10MB', subida: 'PLAN_10MB' }]);
    expect(f.at(-1)).toEqual({ plan: 'PLAN VIEJO', velocidad: '', bajada: 'PLAN_10MB', subida: 'PLAN_10MB',
                               sugerido: false, seVende: false, sugeridos: { bajada: '', subida: '' },
                               kbps: { bajada: null, subida: null } });
  });

  it('sin respuesta del motor no hay filas inventadas', () => {
    expect(filasDePerfiles(null, [])).toEqual([]);
  });
});
