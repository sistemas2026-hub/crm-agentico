import { describe, it, expect, vi } from 'vitest';

// operadores.js importa api-helpers.js, que lee $env/dynamic/private: este
// harness no lo resuelve (ver vitest.config.js). La funcion probada no lo usa.
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: vi.fn() }));
const { validarReasignacion } = await import('./operadores.js');

/**
 * B3.4 (T4): lo que el proxy de reasignar decide antes de ir al motor. El motor
 * vuelve a exigir el rol; esto fija la primera barrera.
 */
const operadores = [
  { usuario_id: 'u-luis', nombre: 'Luis Rojas' },
  { usuario_id: 'u-ana', nombre: 'Ana Perez' }
];

describe('validarReasignacion', () => {
  it('un operador que no es ADMIN recibe 403, aunque mande todo lo demas', () => {
    const r = validarReasignacion({ rol: 'USER', motivo: 'turno', destinoId: 'u-luis', operadores });
    expect(r).toMatchObject({ ok: false, status: 403, codigo: 'no_es_admin' });
  });

  it('sin rol en la sesion tambien es 403', () => {
    const r = validarReasignacion({ rol: undefined, motivo: 'turno', destinoId: 'u-luis', operadores });
    expect(r).toMatchObject({ ok: false, status: 403 });
  });

  it('ADMIN sin motivo (o solo espacios) recibe 400', () => {
    const r = validarReasignacion({ rol: 'ADMIN', motivo: '   ', destinoId: 'u-luis', operadores });
    expect(r).toMatchObject({ ok: false, status: 400, codigo: 'sin_motivo' });
  });

  it('un destino que no es operador activo de la organizacion recibe 400', () => {
    const r = validarReasignacion({ rol: 'ADMIN', motivo: 'turno', destinoId: 'u-de-otra-org', operadores });
    expect(r).toMatchObject({ ok: false, status: 400, codigo: 'destino_invalido' });
  });

  it('el nombre del destino sale de la lista de la organizacion, no del pedido', () => {
    const r = validarReasignacion({ rol: 'admin', motivo: ' cambio de turno ', destinoId: 'u-luis', operadores });
    expect(r).toEqual({ ok: true, motivo: 'cambio de turno', destino: { usuario_id: 'u-luis', nombre: 'Luis Rojas' } });
  });
});
