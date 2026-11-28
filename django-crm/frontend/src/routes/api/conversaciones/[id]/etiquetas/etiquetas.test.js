import { describe, it, expect, vi } from 'vitest';

/**
 * Etiquetas del equipo y «leída» (11/11/2026): el salto que el motor no ve.
 * Que las claves lleguen tal cual, que el autor salga de la SESIÓN y no del
 * cuerpo, que `leida` llegue como booleano estricto, y que sin sesión no se
 * llegue al motor.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/autor.js', () => ({
  autorDeSesion: () => ({ autor: 'Ana', autor_usuario_id: 'u-ana' })
}));

const { PUT } = await import('./+server.js');
const { POST } = await import('../leida/+server.js');

/** @param {any} manejador @param {any} cuerpo @param {any} [user] @param {number} [status] */
async function llamar(manejador, cuerpo, user = { id: 'u-ana' }, status = 200) {
  const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status }));
  const r = await manejador(/** @type {any} */ ({
    request: { json: async () => cuerpo }, params: { id: 'c1' }, locals: { user }, fetch
  }));
  const llamada = /** @type {any} */ (fetch.mock.calls[0]);
  return { r, fetch, url: llamada?.[0], init: llamada?.[1], body: llamada ? JSON.parse(llamada[1].body) : null };
}

describe('PUT /api/conversaciones/[id]/etiquetas', () => {
  it('manda las claves al motor con el autor de la sesión, no el del cuerpo', async () => {
    const { url, init, body } = await llamar(PUT, { etiquetas: ['vip', 'moroso'], autor: 'Impostor' });
    expect(url).toBe('http://motor/conversaciones/c1/etiquetas');
    expect(init.method).toBe('PUT');
    expect(body).toEqual({ tenant: 'empresa', etiquetas: ['vip', 'moroso'], autor: 'Ana',
      autor_usuario_id: 'u-ana' });
  });

  it('una lista vacía viaja vacía: es «sacá todas»', async () => {
    const { body } = await llamar(PUT, { etiquetas: [] });
    expect(body.etiquetas).toEqual([]);
  });

  it('lo que no es una lista no llega al motor', async () => {
    const { r, fetch } = await llamar(PUT, { etiquetas: 'vip' });
    expect(r.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('el rechazo del motor (clave fuera del catálogo) vuelve con su código', async () => {
    const { r } = await llamar(PUT, { etiquetas: ['x'] }, { id: 'u-ana' }, 400);
    expect(r.status).toBe(400);
  });

  it('sin sesión no llega al motor', async () => {
    const { r, fetch } = await llamar(PUT, { etiquetas: ['vip'] }, null);
    expect(r.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('POST /api/conversaciones/[id]/leida', () => {
  it('leída: true llega como true', async () => {
    const { url, body } = await llamar(POST, { leida: true });
    expect(url).toBe('http://motor/conversaciones/c1/leida');
    expect(body).toEqual({ tenant: 'empresa', leida: true });
  });

  it('cualquier otra cosa es «no leída», nunca un "false" en texto', async () => {
    expect((await llamar(POST, { leida: false })).body.leida).toBe(false);
    expect((await llamar(POST, { leida: 'true' })).body.leida).toBe(false);
  });

  it('el 409 del motor (nada que volver a contar) llega tal cual, sin sello', async () => {
    const { r } = await llamar(POST, { leida: false }, { id: 'u-ana' }, 409);
    expect(r.status).toBe(409);
    expect((await r.json()).marcada_en).toBeUndefined();
  });

  it('una marca aplicada vuelve sellada con la hora de este servidor', async () => {
    const antes = Date.now();
    const { r } = await llamar(POST, { leida: true });
    const sello = Date.parse((await r.json()).marcada_en);
    expect(sello).toBeGreaterThanOrEqual(antes);
  });

  it('sin sesión no llega al motor', async () => {
    const { r, fetch } = await llamar(POST, { leida: true }, null);
    expect(r.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
});
