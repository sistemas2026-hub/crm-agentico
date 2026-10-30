import { describe, it, expect, vi } from 'vitest';

/**
 * Las menciones de una nota interna (30/10/2026). El salto que ni el motor ni
 * Django ven: que la nota guardada dispare el aviso, solo si tiene una «@», y
 * que un aviso fallido NO tumbe la nota, que ya está guardada.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/autor.js', () => ({
  autorDeSesion: () => ({ autor: 'Ana', autor_usuario_id: 'u-ana' }),
  claveIdempotencia: (c) => c
}));
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { POST } = await import('./+server.js');

async function nota(mensaje) {
  const fetch = vi.fn(async () => new Response('{"ok":true}', { status: 201 }));
  const r = await POST(/** @type {any} */ ({
    params: { id: 'c-1' }, locals: { user: { id: 'u' } }, fetch, cookies: {},
    request: { json: async () => ({ mensaje }) }
  }));
  return { status: r.status, datos: await r.json() };
}

describe('POST /api/conversaciones/[id]/nota con menciones', () => {
  it('una «@» avisa, con la conversación y el texto', async () => {
    apiRequest.mockReset().mockResolvedValue({ avisados: 1 });
    const { status, datos } = await nota('@luis mirá esta');
    expect(status).toBe(201);
    expect(apiRequest.mock.calls[0][0]).toBe('/notifications/mencion-conversacion/');
    expect(apiRequest.mock.calls[0][1].body).toEqual({ conversation_id: 'c-1', texto: '@luis mirá esta' });
    expect(datos.avisados).toBe(1);
  });
  it('sin «@» no pide nada al CRM', async () => {
    apiRequest.mockReset();
    await nota('anotación común');
    expect(apiRequest).not.toHaveBeenCalled();
  });
  it('si el aviso falla, la nota igual queda guardada', async () => {
    apiRequest.mockReset().mockRejectedValue(new Error('caído'));
    const { status, datos } = await nota('@luis');
    expect(status).toBe(201);
    expect(datos.avisados).toBeNull();
  });
});
