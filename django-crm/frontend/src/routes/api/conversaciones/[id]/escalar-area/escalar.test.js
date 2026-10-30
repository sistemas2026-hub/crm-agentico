import { describe, it, expect, vi } from 'vitest';

/**
 * Escalar a un área (T22). El salto que el motor no ve: que el autor salga de
 * la SESIÓN y no del cuerpo, y que área, motivo y nota lleguen tal cual.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/autor.js', () => ({
  autorDeSesion: () => ({ autor: 'Ana', autor_usuario_id: 'u-ana' })
}));

const { POST } = await import('./+server.js');

async function enviado(cuerpo, user = { id: 'u-ana' }) {
  const fetch = vi.fn(async () => new Response('{"escalada":true}', { status: 200 }));
  const r = await POST(/** @type {any} */ ({
    request: { json: async () => cuerpo }, params: { id: 'c1' }, locals: { user }, fetch
  }));
  return { r, fetch, body: fetch.mock.calls.length ? JSON.parse(/** @type {any} */ (fetch.mock.calls[0])[1].body) : null };
}

describe('POST /api/conversaciones/[id]/escalar-area', () => {
  it('manda área, motivo y nota, con el autor de la sesión', async () => {
    const { body } = await enviado({
      area: 'soporte_tecnico', motivo: ' no levanta ', nota: 'reinicié', autor: 'Impostor'
    });
    expect(body).toMatchObject({ area: 'soporte_tecnico', motivo: 'no levanta', nota: 'reinicié',
      autor: 'Ana', autor_usuario_id: 'u-ana', tenant: 'empresa' });
  });
  it('sin sesión no llega al motor', async () => {
    const { r, fetch } = await enviado({ area: 'x' }, null);
    expect(r.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
});
