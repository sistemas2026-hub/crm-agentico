import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { actions } = await import('./+page.server.js');

/**
 * Bodega atiende o rechaza un pedido (18/10/2026): el salto de la acción de la
 * página al backend. Lo que el backend decide —rechazo sin nota, 409 si otro ya
 * lo resolvió— está probado en `test_reportes_de_lo_que_escribio_el_tecnico.py`;
 * acá se mide que la acción mande lo que el formulario dijo y que el error del
 * backend llegue a la pantalla con su texto.
 */
function evento(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({
    request: { formData: async () => f },
    cookies: { get: () => 'token' }
  });
}

describe('resolver un pedido desde Reportes', () => {
  beforeEach(() => { apiRequest.mockReset(); });

  it('manda el pedido, el estado y la nota al backend', async () => {
    apiRequest.mockResolvedValue({ estado: 'atendido' });
    const r = await actions.resolverPedido(
      evento({ pedido: 'p-1', estado: 'atendido', nota: '  sale a las 2  ' })
    );
    const [endpoint, opciones] = apiRequest.mock.calls[0];
    expect(endpoint).toBe('/campo/inventario/pedidos/p-1/resolver/');
    expect(opciones).toEqual({ method: 'POST', body: { estado: 'atendido', nota: 'sale a las 2' } });
    expect(r).toEqual({ hecho: 'Pedido atendido.' });
  });

  it('un rechazo dice que se rechazó', async () => {
    apiRequest.mockResolvedValue({ estado: 'rechazado' });
    const r = await actions.resolverPedido(
      evento({ pedido: 'p-1', estado: 'rechazado', nota: 'sin stock' })
    );
    expect(r).toEqual({ hecho: 'Pedido rechazado.' });
  });

  it('si otro ya lo resolvió, la pantalla recibe el 409 con el texto del backend', async () => {
    const e = Object.assign(new Error('Error 409: x'), {
      status: 409,
      body: { detail: 'Este pedido ya está atendido: lo decidió otra persona y no se cambia desde acá.' }
    });
    apiRequest.mockRejectedValue(e);
    const r = /** @type {any} */ (await actions.resolverPedido(
      evento({ pedido: 'p-1', estado: 'rechazado', nota: 'x' })
    ));
    expect(r.status).toBe(409);
    expect(r.data.error).toContain('ya está atendido');
  });

  it('un rechazo sin nota vuelve con el motivo del backend', async () => {
    const e = Object.assign(new Error('Error 400: x'), {
      status: 400, body: { detail: 'Para rechazar un pedido hay que decir por qué.' }
    });
    apiRequest.mockRejectedValue(e);
    const r = /** @type {any} */ (
      await actions.resolverPedido(evento({ pedido: 'p-1', estado: 'rechazado', nota: '' }))
    );
    expect(r.status).toBe(400);
    expect(r.data.error).toBe('Para rechazar un pedido hay que decir por qué.');
  });
});
