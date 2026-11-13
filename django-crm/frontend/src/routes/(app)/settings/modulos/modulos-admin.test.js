import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * /settings/modulos es de ADMIN en el servidor (12/11/2026): un miembro que
 * escribe la URL vuelve al hub sin que se lea nada, y su POST se rechaza sin
 * viajar al backend.
 */
vi.mock('$env/dynamic/private', () => ({ env: {} }));
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { load, actions } = await import('./+page.server.js');

const cookies = /** @type {any} */ ({ get: () => undefined });
const pedido = () =>
  /** @type {any} */ ({ formData: async () => { const f = new FormData(); f.append('oculto', 'goals'); return f; } });

beforeEach(() => {
  apiRequest.mockReset();
});

describe('/settings/modulos', () => {
  it('un USER que abre la página vuelve al hub y no se lee nada', async () => {
    await expect(load(/** @type {any} */ ({ locals: { profile: { role: 'USER' } }, cookies })))
      .rejects.toMatchObject({ status: 303, location: '/settings' });
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un ADMIN la abre con lo que la empresa tiene oculto', async () => {
    apiRequest.mockResolvedValue({ modulos_ocultos: ['goals'] });
    const d = await load(/** @type {any} */ ({ locals: { profile: { role: 'ADMIN' } }, cookies }));
    expect(d).toEqual({ ocultos: ['goals'] });
  });

  it('el POST de un USER es 403 y no viaja', async () => {
    const r = /** @type {any} */ (await actions.guardar(
      /** @type {any} */ ({ request: pedido(), locals: { profile: { role: 'USER' } }, cookies })
    ));
    expect(r?.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
