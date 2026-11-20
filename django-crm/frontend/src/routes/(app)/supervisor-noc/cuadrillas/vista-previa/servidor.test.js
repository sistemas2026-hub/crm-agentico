/**
 * La ruta de la vista previa del armado (21/10/2026): rol de gestión, y la
 * fecha viaja tal cual a la API. CLAUDE.md §6: la capa servidor es donde un
 * dato que el backend manda bien se pierde sin que ninguna prueba de backend
 * lo vea.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));

const { GET } = await import('./+server.js');

/** @param {string} rol @param {string} [fecha] */
const evento = (rol, fecha = '2026-10-22') => /** @type {any} */ ({
  url: new URL(`http://x/supervisor-noc/cuadrillas/vista-previa?fecha=${fecha}`),
  cookies: { get: () => 'token' },
  locals: { user: { id: 'u' }, profile: { role: rol } }
});

beforeEach(() => {
  apiRequest.mockReset();
});

describe('vista previa del armado', () => {
  it('pide a la API la fecha que se eligió y devuelve lo que contesta', async () => {
    apiRequest.mockResolvedValue({ fecha: '2026-10-22', trabaja: true, cuadrillas: [] });
    const r = await GET(evento('OPERACIONES'));
    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/jornada/vista-previa/?fecha=2026-10-22');
    expect(r.status).toBe(200);
    expect((await r.json()).trabaja).toBe(true);
  });

  it('sin rol de gestión no le pregunta nada a la API', async () => {
    const r = await GET(evento('USER'));
    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('el error del backend llega como frase y con su estado', async () => {
    apiRequest.mockRejectedValue(Object.assign(new Error('x'), {
      status: 400, body: { detail: 'La fecha va como AAAA-MM-DD.' } }));
    const r = await GET(evento('ADMIN', 'mal'));
    expect(r.status).toBe(400);
    expect((await r.json()).error).toContain('AAAA-MM-DD');
  });
});
