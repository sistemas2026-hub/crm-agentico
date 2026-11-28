/**
 * La ruta de «qué crearía el Supervisor» (23/10/2026): rol de gestión, y lo
 * que contesta la API llega entero. CLAUDE.md §6: la capa servidor es donde un
 * dato que el backend manda bien se pierde sin que ninguna prueba de backend
 * lo vea.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));

const { GET } = await import('./+server.js');

/** @param {string} rol */
const evento = (rol) => /** @type {any} */ ({
  url: new URL('http://x/supervisor-noc/despacho/vista-previa'),
  cookies: { get: () => 'token' },
  locals: { user: { id: 'u' }, profile: { role: rol } }
});

beforeEach(() => {
  apiRequest.mockReset();
});

describe('qué crearía el Supervisor', () => {
  it('pide la vista previa y devuelve las tres listas', async () => {
    apiRequest.mockResolvedValue({
      hora_de_corte: '12:00', porque: '',
      crear: [{ caso: 'a' }], no_se_crea: [{ caso: 'b' }], atadas: [{ caso: 'c' }]
    });
    const r = await GET(evento('OPERACIONES'));
    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/ordenes/vista-previa/');
    const d = await r.json();
    expect([d.crear.length, d.no_se_crea.length, d.atadas.length]).toEqual([1, 1, 1]);
  });

  it('sin rol de gestión no le pregunta nada a la API', async () => {
    const r = await GET(evento('USER'));
    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
