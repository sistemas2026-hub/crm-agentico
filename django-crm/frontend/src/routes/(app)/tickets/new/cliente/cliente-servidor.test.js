import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La búsqueda del cliente de "Nuevo ticket" viaja en el CUERPO (28/10/2026,
 * revisor-de-pii): es la cédula o el nombre de una persona, y en la URL
 * quedaría en cualquier registro de acceso del camino público.
 */

const buscarClientes = vi.fn();
vi.mock('$lib/server/v2/ticket-desde-dexter.js', () => ({
  buscarClientes: (...a) => buscarClientes(...a)
}));

const ruta = await import('./+server.js');

/** @param {any} cuerpo */
const pedido = (cuerpo) =>
  /** @type {any} */ ({
    request: { json: async () => cuerpo },
    locals: {},
    fetch: vi.fn()
  });

describe('POST /tickets/new/cliente', () => {
  beforeEach(() => {
    buscarClientes.mockReset();
    buscarClientes.mockResolvedValue({ ok: true, resultados: [], mas: false, cargando: false });
  });

  it('lee la búsqueda del cuerpo y la pasa tal cual', async () => {
    const r = await ruta.POST(pedido({ q: 'maria lopez' }));
    expect(buscarClientes.mock.calls[0][2]).toBe('maria lopez');
    expect(await r.json()).toEqual({ ok: true, resultados: [], mas: false, cargando: false });
  });

  it('un cuerpo roto o sin q busca vacío (y el puente lo rechaza por corto)', async () => {
    await ruta.POST(/** @type {any} */ ({
      request: { json: async () => { throw new Error('no es JSON'); } },
      locals: {},
      fetch: vi.fn()
    }));
    await ruta.POST(pedido({ q: 123 }));
    expect(buscarClientes.mock.calls.map((c) => c[2])).toEqual(['', '']);
  });

  it('por la URL ya no se busca: no hay GET', () => {
    expect(/** @type {any} */ (ruta).GET).toBeUndefined();
  });
});
