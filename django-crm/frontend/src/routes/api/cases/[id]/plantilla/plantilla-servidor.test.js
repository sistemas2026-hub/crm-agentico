import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La plantilla desde el ticket (28/10/2026): lo que llega al motor, y que el
 * texto quede en el historial del ticket SIN marcar la primera respuesta (esa
 * la marca el motor, y sólo si Meta aceptó el mensaje).
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor:5000' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => ({ 'X-T': 't', ...h }) }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/autor.js', () => ({
  autorDeSesion: () => ({ autor: 'Ana', autor_usuario_id: 'u-1' }),
  claveIdempotencia: (c) => c || 'clave-nueva'
}));
const replyToTicket = vi.fn();
vi.mock('$lib/server/v2/tickets.js', () => ({ replyToTicket: (...a) => replyToTicket(...a) }));

const { POST } = await import('./+server.js');

/** @param {any} cuerpo @param {any} fetch @param {any} [locals] */
const pedido = (cuerpo, fetch, locals = { user: { email: 'a@x.test' } }) =>
  /** @type {any} */ ({
    params: { id: 'caso-1' },
    locals,
    fetch,
    cookies: {},
    request: { json: async () => cuerpo }
  });

/** @param {number} status @param {any} cuerpo */
const motor = (status, cuerpo) =>
  vi.fn(async () => ({ status, ok: status < 300, json: async () => cuerpo }));

describe('POST /api/cases/[id]/plantilla', () => {
  beforeEach(() => {
    replyToTicket.mockReset();
    replyToTicket.mockResolvedValue({});
  });

  it('va al motor POR EL CASO, con el autor de la sesión y la clave de la pantalla', async () => {
    const fetch = motor(201, { ok: true, texto: 'Hola, sobre tu caso: listo', resultado: 'aceptado' });
    await POST(pedido({ plantilla: 'seguimiento_caso', variables: ['listo'], clave_idempotencia: 'k-1' }, fetch));
    const [url, init] = /** @type {any} */ (fetch.mock.calls[0]);
    expect(url).toBe('http://motor:5000/casos/caso-1/plantilla');
    expect(JSON.parse(init.body)).toEqual({
      tenant: 'empresa',
      plantilla: 'seguimiento_caso',
      variables: ['listo'],
      autor: 'Ana',
      autor_usuario_id: 'u-1',
      clave_idempotencia: 'k-1'
    });
  });

  it('si el motor la guardó, queda en el historial SIN marcar la primera respuesta', async () => {
    const fetch = motor(201, { ok: true, texto: 'Hola, sobre tu caso: listo', resultado: 'rechazado' });
    const r = await POST(pedido({ plantilla: 'seguimiento_caso', variables: ['listo'] }, fetch));
    expect(replyToTicket).toHaveBeenCalledTimes(1);
    expect(replyToTicket.mock.calls[0][2]).toEqual({
      body: 'Hola, sobre tu caso: listo',
      sinPrimeraRespuesta: true
    });
    expect((await r.json()).en_historial).toBe(true);
  });

  it('un rechazo del motor (400) no deja nada en el historial', async () => {
    const fetch = motor(400, { error: 'necesita 1 variable(s)' });
    const r = await POST(pedido({ plantilla: 'seguimiento_caso', variables: [] }, fetch));
    expect(r.status).toBe(400);
    expect(replyToTicket).not.toHaveBeenCalled();
  });

  it('un reintento (200, ya existía) no la duplica en el historial', async () => {
    const fetch = motor(200, { ok: true, ya_existia: true, texto: 'Hola' });
    await POST(pedido({ plantilla: 'seguimiento_caso', variables: ['x'] }, fetch));
    expect(replyToTicket).not.toHaveBeenCalled();
  });

  it('sin respuesta del motor: incierto, y dice que no se reenvíe', async () => {
    const fetch = vi.fn(async () => {
      throw new Error('timeout');
    });
    const r = await POST(pedido({ plantilla: 'seguimiento_caso', variables: ['x'] }, fetch));
    const d = await r.json();
    expect(r.status).toBe(502);
    expect(d.incierto).toBe(true);
    expect(d.error).toMatch(/No la mandes de nuevo/);
    expect(replyToTicket).not.toHaveBeenCalled();
  });

  it('sin plantilla o sin sesión no sale nada', async () => {
    const fetch = vi.fn();
    expect((await POST(pedido({ plantilla: ' ' }, fetch))).status).toBe(400);
    expect((await POST(pedido({ plantilla: 'x' }, fetch, {}))).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
});
