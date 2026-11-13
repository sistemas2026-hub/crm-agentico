import { describe, it, expect, vi } from 'vitest';

/**
 * DELETE /api/conversaciones/[id] (12/11/2026). Borrar datos es crítico
 * (PRD §2): solo un ADMIN pasa de acá, por el rol de la SESIÓN. Lo que sigue
 * —que el canal no sea real— lo decide el motor, y su 403 vuelve tal cual.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));

const { DELETE } = await import('./+server.js');

/** @param {any} locals @param {Response} [respuesta] */
async function borrar(locals, respuesta) {
  const fetch = vi.fn(async () => respuesta ?? new Response(null, { status: 204 }));
  const r = await DELETE(/** @type {any} */ ({ params: { id: 'c 1' }, locals, fetch }));
  return { r, fetch };
}

const admin = { user: { id: 'u1' }, profile: { role: 'ADMIN' } };

describe('DELETE /api/conversaciones/[id]', () => {
  it('un ADMIN llega al motor con el id y el tenant codificados', async () => {
    const { r, fetch } = await borrar(admin);
    expect(r.status).toBe(204);
    expect(/** @type {any} */ (fetch.mock.calls[0])[0]).toBe('http://motor/conversaciones/c%201?tenant=empresa');
    expect(/** @type {any} */ (fetch.mock.calls[0])[1].method).toBe('DELETE');
  });

  it('un USER no llega al motor', async () => {
    for (const profile of [{ role: 'USER' }, undefined, { role: '' }]) {
      const { r, fetch } = await borrar({ user: { id: 'u2' }, profile });
      expect(r.status).toBe(403);
      expect(fetch).not.toHaveBeenCalled();
    }
  });

  it('sin sesión, 401', async () => {
    const { r, fetch } = await borrar({ user: null });
    expect(r.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('el 403 del motor (canal real) vuelve con su código', async () => {
    const respuesta = new Response(JSON.stringify({ error: 'no', codigo: 'canal_real' }), { status: 403 });
    const { r } = await borrar(admin, respuesta);
    expect(r.status).toBe(403);
    expect((await r.json()).codigo).toBe('canal_real');
  });
});
