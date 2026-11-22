import { describe, it, expect, vi, beforeEach } from 'vitest';

const leerDestinatarios = vi.fn();
vi.mock('$lib/server/v2/fallas-de-red.js', () => ({ leerDestinatarios }));

const { GET } = await import('./+server.js');

const ID = '0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d';

/** @param {string} role @param {string} [id] */
const evento = (role, id = ID) => /** @type {any} */ ({
  params: { id },
  locals: { user: { id: 1 }, profile: { role } },
  cookies: {}
});

beforeEach(() => {
  leerDestinatarios.mockReset().mockResolvedValue({
    fase: 'caida', total: 1, destinatarios: [{ servicio: '101', cliente: 'María', pendiente: false }]
  });
});

describe('GET /supervisor-noc/fallas/[id]/destinatarios', () => {
  it('solo gestión, y sin preguntarle al backend', async () => {
    const r = await GET(evento('AGENT'));
    expect(r.status).toBe(403);
    expect(leerDestinatarios).not.toHaveBeenCalled();
  });

  it('un id que no es de una caída no sale', async () => {
    const r = await GET(evento('ADMIN', '../otra-cosa'));
    expect(r.status).toBe(400);
    expect(leerDestinatarios).not.toHaveBeenCalled();
  });

  it('devuelve lo que dice el backend, sin guardarlo en caché', async () => {
    const r = await GET(evento('OPERACIONES'));
    expect(r.status).toBe(200);
    expect(r.headers.get('cache-control')).toBe('no-store');
    expect((await r.json()).destinatarios[0].servicio).toBe('101');
    expect(leerDestinatarios).toHaveBeenCalledWith({ cookies: {} }, ID);
  });

  it('sin aviso aprobado lo dice en palabras, con el estado del backend', async () => {
    leerDestinatarios.mockRejectedValue({ status: 404, body: { error: 'SIN_AVISO' } });
    const r = await GET(evento('ADMIN'));
    expect(r.status).toBe(404);
    expect((await r.json()).error).toBe('Esta caída no tiene un aviso aprobado.');
  });
});
