import { describe, expect, it, vi } from 'vitest';

/**
 * EL DINERO DE LOS TÉCNICOS (26/11/2026). Lo que se afirma atraviesa
 * formulario → acción → API: qué cifra le llega al servidor y qué ve la
 * página cuando la API falla, no que las funciones existan.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { actions, load } = await import('./+page.server.js');

/** @param {Record<string, string>} campos */
const pedido = (campos) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({ request: { formData: async () => f }, cookies: { get: () => 'token' } });
};

describe('Dinero de los técnicos: leer', () => {
  it('lo que dice el backend llega a la página tal cual', async () => {
    apiRequest.mockReset();
    const tecnicos = [{ tecnico: { id: 'p-1', nombre: 'Dilan Moreno' }, pendiente: 105000,
      ordenes: [{ orden_id: 'o-1', numero: 11, cliente: 'X', pendiente: 105000, cobrado: 105000,
        entregado: 0, conceptos: [{ titulo: 'Valor de la instalación', valor: 80000 }] }] }];
    apiRequest.mockResolvedValue({ configurado: true, tecnicos, ultimas: [] });
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ cookies: { get: () => 't' } })));
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dinero/');
    expect(d.tecnicos).toEqual(tecnicos);
    expect(d.error).toBe('');
  });

  it('si la API falla NO dice «nadie debe nada»: dice el error', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue(Object.assign(new Error('x'), { status: 500, body: { detail: 'Se cayó' } }));
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ cookies: { get: () => 't' } })));
    expect(d.error).toBe('Se cayó');
    expect(d.configurado).toBe(true);
  });
});

describe('Dinero de los técnicos: recibir', () => {
  it('manda el técnico y la cifra de CADA orden tal como se vio', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recibidas: 2, tecnicos: [], ultimas: [] });
    const ordenes = [{ orden_id: 'o-1', monto: 105000 }, { orden_id: 'o-2', monto: 50000 }];
    const r = /** @type {any} */ (await actions.recibir(pedido({ tecnico_id: 'p-1', ordenes: JSON.stringify(ordenes) })));
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dinero/recibir/');
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'POST', body: { tecnico_id: 'p-1', ordenes } });
    expect(r).toEqual({ recibido: true, tecnico: 'p-1', total: 155000, recibidas: 2 });
  });

  it('si la cifra cambió (409) lo dice y no inventa un «recibido»', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue(Object.assign(new Error('x'), {
      status: 409, body: { detail: 'La OT-52 cambió: ahora son $50.000. Recarga la página y vuelve a contar.' } }));
    const r = /** @type {any} */ (await actions.recibir(pedido({ tecnico_id: 'p-1',
      ordenes: JSON.stringify([{ orden_id: 'o-2', monto: 70000 }]) })));
    expect(r.status).toBe(409);
    expect(r.data.error).toContain('OT-52 cambió');
    expect(r.data.recibido).toBeUndefined();
  });

  it.each([
    [{ tecnico_id: 'p-1', ordenes: 'no es json' }],
    [{ tecnico_id: 'p-1', ordenes: '[]' }],
    [{ ordenes: JSON.stringify([{ orden_id: 'o-1', monto: 1 }]) }],
    [{ tecnico_id: 'p-1', ordenes: JSON.stringify([{ orden_id: 'o-1', monto: 'mucho' }]) }]
  ])('un formulario incompleto no llega a la API (%o)', async (campos) => {
    apiRequest.mockReset();
    const r = /** @type {any} */ (await actions.recibir(pedido(campos)));
    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
