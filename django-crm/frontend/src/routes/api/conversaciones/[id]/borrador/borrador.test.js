import { describe, it, expect, vi } from 'vitest';

/** El intermediario del borrador (30/10/2026): pide, devuelve, no inventa. */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));

const { POST } = await import('./+server.js');

describe('POST /api/conversaciones/[id]/borrador', () => {
  it('devuelve lo que propone el motor, con su estado', async () => {
    const fetch = vi.fn(async () => new Response('{"borrador":"Ya lo reviso."}', { status: 200 }));
    const r = await POST(/** @type {any} */ ({ params: { id: 'c1' }, locals: { user: { id: 'u' } }, fetch }));
    expect(r.status).toBe(200);
    expect((await r.json()).borrador).toBe('Ya lo reviso.');
    expect(JSON.parse(/** @type {any} */ (fetch.mock.calls[0])[1].body)).toEqual({ tenant: 'empresa' });
  });
  it('un rechazo del motor pasa tal cual, sin inventar un texto', async () => {
    const fetch = vi.fn(async () => new Response('{"error":"No hay sugerencia: x."}', { status: 409 }));
    const r = await POST(/** @type {any} */ ({ params: { id: 'c1' }, locals: { user: { id: 'u' } }, fetch }));
    expect(r.status).toBe(409);
    expect((await r.json()).borrador).toBeUndefined();
  });
  it('sin sesión no llega al motor', async () => {
    const fetch = vi.fn();
    const r = await POST(/** @type {any} */ ({ params: { id: 'c1' }, locals: {}, fetch }));
    expect(r.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
});
