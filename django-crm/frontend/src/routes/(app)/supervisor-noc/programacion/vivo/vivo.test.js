import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * PROGRAMACIÓN VIVA (30/10/2026): lo publicado del día, para que la pantalla
 * se actualice sola. Solo quien gestiona; si el backend falla, no se borra lo
 * que se ve.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { GET } = await import('./+server.js');

/** @param {string} url @param {string} rol */
const pedido = (url, rol) =>
  /** @type {any} */ ({ url: new URL(url), cookies: { get: () => 't' }, locals: { profile: { role: rol } } });

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({ fecha: '2026-10-30', cuadrillas: [] });
});

describe('Programación viva', () => {
  it('quien gestiona recibe lo publicado del día, sin cache', async () => {
    const r = await GET(pedido('http://x/vivo?dia=2026-10-30', 'SUPERVISOR'));
    expect(r.status).toBe(200);
    expect(r.headers.get('cache-control')).toBe('no-store');
    expect(await r.json()).toEqual({ publicado: { fecha: '2026-10-30', cuadrillas: [] } });
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-30');
  });

  it('quien no gestiona no recibe nada, y sin día tampoco', async () => {
    expect((await GET(pedido('http://x/vivo?dia=2026-10-30', 'USER'))).status).toBe(403);
    expect((await GET(pedido('http://x/vivo?dia=ayer', 'ADMIN'))).status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('si el backend falla, 502: la pantalla se queda con lo último', async () => {
    apiRequest.mockRejectedValue(new Error('caído'));
    expect((await GET(pedido('http://x/vivo?dia=2026-10-30', 'ADMIN'))).status).toBe(502);
  });
});
