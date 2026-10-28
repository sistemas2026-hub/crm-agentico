import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LA CARGA DE PROGRAMACIÓN (28/10/2026): pide al backend lo publicado del día,
 * con el día de la URL o el de la empresa, y solo para quien gestiona.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2026-10-28' }));

const { load } = await import('./+page.server.js');

const PUBLICADO = { fecha: '2026-10-28', cuadrillas: [], con_alguien_que_no_sale: [], esperan: [], cuentas: {} };

/** @param {string} url @param {string} rol */
const ctx = (url, rol) =>
  /** @type {any} */ ({
    url: new URL(url),
    cookies: { get: () => 'token' },
    locals: { org: { id: 'org-1' }, profile: { role: rol } }
  });

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue(PUBLICADO);
});

describe('Programación: la carga', () => {
  it('sin día en la URL pide el de la empresa', async () => {
    const d = /** @type {any} */ (await load(ctx('http://x/supervisor-noc/programacion', 'ADMIN')));

    expect(d.dia).toBe('2026-10-28');
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-28');
    expect(d.publicado).toEqual(PUBLICADO);
  });

  it('con día en la URL pide ese', async () => {
    await load(ctx('http://x/supervisor-noc/programacion?dia=2026-10-30', 'SUPERVISOR'));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-30');
  });

  it('un día mal escrito no viaja: usa el de la empresa', async () => {
    await load(ctx('http://x/supervisor-noc/programacion?dia=mañana', 'ADMIN'));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-28');
  });

  it('quien no gestiona no pide nada', async () => {
    const d = /** @type {any} */ (await load(ctx('http://x/supervisor-noc/programacion', 'USER')));

    expect(d.puedeVer).toBe(false);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('si el backend no contesta, lo dice en vez de mostrar vacío', async () => {
    apiRequest.mockRejectedValue(new Error('caído'));

    const d = /** @type {any} */ (await load(ctx('http://x/supervisor-noc/programacion', 'ADMIN')));

    expect(d.publicado).toBe(null);
    expect(d.error).toBe(true);
  });
});
