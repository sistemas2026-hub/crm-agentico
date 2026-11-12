import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * /settings/modulos del lado del servidor (12/11/2026): quién guarda, qué
 * viaja al backend y qué pasa cuando no se puede leer.
 */
vi.mock('$env/dynamic/private', () => ({ env: {} }));
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { guardarModulosOcultos, leerModulosOcultos, SOLO_ADMIN } = await import('./modulos.js');

const cookies = /** @type {any} */ ({ get: () => undefined });
const formCon = (...claves) => {
  const f = new FormData();
  for (const c of claves) f.append('oculto', c);
  return f;
};

beforeEach(() => {
  apiRequest.mockReset();
});

describe('guardar', () => {
  it('un USER no guarda y no se viaja al backend', async () => {
    const r = await guardarModulosOcultos({ cookies }, 'USER', formCon('accounts'));
    expect(r).toEqual({ ok: false, status: 403, error: SOLO_ADMIN });
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('sin rol tampoco (falla cerrado)', async () => {
    const r = await guardarModulosOcultos({ cookies }, undefined, formCon());
    expect(r.ok).toBe(false);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un ADMIN manda exactamente lo marcado y recibe lo que guardó el backend', async () => {
    apiRequest.mockResolvedValue({ modulos_ocultos: ['accounts', 'timesheet'] });
    const r = await guardarModulosOcultos({ cookies }, 'ADMIN', formCon('timesheet', 'accounts'));
    expect(apiRequest).toHaveBeenCalledWith(
      '/org/settings/',
      { method: 'PATCH', body: { modulos_ocultos: ['timesheet', 'accounts'] } },
      { cookies }
    );
    expect(r).toEqual({ ok: true, ocultos: ['accounts', 'timesheet'] });
  });

  it('desmarcar todo manda la lista vacía (volver a ver todo)', async () => {
    apiRequest.mockResolvedValue({ modulos_ocultos: [] });
    await guardarModulosOcultos({ cookies }, 'ADMIN', formCon());
    expect(apiRequest.mock.calls[0][1].body).toEqual({ modulos_ocultos: [] });
  });

  it('una clave que la pantalla no ofrece no viaja', async () => {
    const r = await guardarModulosOcultos({ cookies }, 'ADMIN', formCon('conversaciones'));
    expect(r.ok).toBe(false);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('el 403 del backend se dice como tal', async () => {
    apiRequest.mockRejectedValue(Object.assign(new Error('x'), { status: 403 }));
    const r = await guardarModulosOcultos({ cookies }, 'ADMIN', formCon('goals'));
    expect(r).toEqual({ ok: false, status: 403, error: SOLO_ADMIN });
  });
});

describe('leer', () => {
  it('lo que tiene la empresa, solo claves conocidas', async () => {
    apiRequest.mockResolvedValue({ modulos_ocultos: ['goals', 'raro'] });
    expect(await leerModulosOcultos({ cookies })).toEqual({ ocultos: ['goals'] });
  });

  it('si no se puede leer es null, no «nada oculto» (guardar desde ahí borraría lo guardado)', async () => {
    apiRequest.mockRejectedValue(new Error('caído'));
    expect(await leerModulosOcultos({ cookies })).toEqual({ ocultos: null });
  });
});
