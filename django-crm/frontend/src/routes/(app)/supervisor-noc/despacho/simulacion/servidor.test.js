/**
 * La ruta de «Simular el día» (24/10/2026): rol de gestión, y la fecha viaja
 * tal cual a la API. CLAUDE.md §6: la capa servidor es donde un dato que el
 * backend manda bien se pierde sin que ninguna prueba de backend lo vea.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));

const { GET } = await import('./+server.js');

/** @param {string} rol @param {string} [fecha] */
const evento = (rol, fecha = '2026-10-26') => /** @type {any} */ ({
  url: new URL(`http://x/supervisor-noc/despacho/simulacion?fecha=${fecha}`),
  cookies: { get: () => 'token' },
  locals: { user: { id: 'u' }, profile: { role: rol } }
});

beforeEach(() => {
  apiRequest.mockReset();
});

describe('simular el día', () => {
  it('pide la fecha que se eligió y devuelve las cuadrillas', async () => {
    apiRequest.mockResolvedValue({ fecha: '2026-10-26', trabaja: true, cuadrillas: [{ cuadrilla: 'Cuadrilla #1' }] });
    const r = await GET(evento('OPERACIONES'));
    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/dia/simulacion/?fecha=2026-10-26');
    expect((await r.json()).cuadrillas).toHaveLength(1);
  });

  it('sin rol de gestión no le pregunta nada a la API', async () => {
    const r = await GET(evento('USER'));
    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
