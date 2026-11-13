import { describe, it, expect, vi } from 'vitest';

/**
 * Rechazar una acción con motivo (12/11/2026). Lo que el motor no exige y el
 * proxy sí: el motivo, y quién rechaza tomado de la SESIÓN y no del cuerpo.
 * Se afirma sobre el cuerpo que sale al motor y el estado que vuelve.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));

const { POST, _MOTIVO_MAXIMO } = await import('./+server.js');

/**
 * @param {any} cuerpo
 * @param {{ user?: any, respuesta?: Response }} [o]
 */
async function rechazar(cuerpo, o = {}) {
  const user = 'user' in o ? o.user : { id: 'u-ana', name: 'Ana', email: 'ana@x.co' };
  const fetch = vi.fn(async () => o.respuesta ?? new Response('{"ok":true,"estado":"rechazada"}', { status: 200 }));
  const r = await POST(/** @type {any} */ ({
    request: { json: async () => cuerpo }, params: { id: 'c1', accion: 'a 1' }, locals: { user }, fetch
  }));
  const llamada = /** @type {any} */ (fetch.mock.calls[0]);
  return {
    r, fetch, cuerpoDe: await r.json(),
    url: llamada ? llamada[0] : null,
    body: llamada ? JSON.parse(llamada[1].body) : null
  };
}

describe('POST /api/conversaciones/[id]/acciones/[accion]/rechazar', () => {
  it('manda el motivo y quién rechaza tomado de la sesión, no del navegador', async () => {
    const { r, body, url, cuerpoDe } = await rechazar({ motivo: '  el cliente ya pagó  ', revisado_por: 'Impostor' });
    expect(url).toBe('http://motor/acciones/propuestas/a%201/rechazar');
    expect(body).toEqual({ tenant: 'empresa', revisado_por: 'Ana', motivo: 'el cliente ya pagó' });
    expect(r.status).toBe(200);
    expect(cuerpoDe.estado).toBe('rechazada');
  });

  it('sin motivo no llega al motor', async () => {
    for (const motivo of [undefined, '', '   ', 42]) {
      const { r, fetch } = await rechazar({ motivo });
      expect(r.status).toBe(400);
      expect(fetch).not.toHaveBeenCalled();
    }
  });

  it('un motivo demasiado largo no llega al motor', async () => {
    const { r, fetch } = await rechazar({ motivo: 'x'.repeat(_MOTIVO_MAXIMO + 1) });
    expect(r.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('sin sesión, 401 y no llega al motor', async () => {
    const { r, fetch } = await rechazar({ motivo: 'no' }, { user: null });
    expect(r.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('una sesión sin nombre ni email no rechaza: no habría a quién atribuirlo', async () => {
    const { r, fetch } = await rechazar({ motivo: 'no' }, { user: { id: 'u', name: '', email: '' } });
    expect(r.status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('el 409 del motor (ya la resolvió otro) vuelve con su estado', async () => {
    const respuesta = new Response(JSON.stringify({ error: 'ya', estado: 'ejecutada_ok' }), { status: 409 });
    const { r, cuerpoDe } = await rechazar({ motivo: 'no' }, { respuesta });
    expect(r.status).toBe(409);
    expect(cuerpoDe.estado).toBe('ejecutada_ok');
  });

  it('motor caído: 502 sin el error crudo', async () => {
    const fetch = vi.fn(async () => { throw new Error('ECONNREFUSED 10.0.0.5:5000'); });
    const r = await POST(/** @type {any} */ ({
      request: { json: async () => ({ motivo: 'no' }) }, params: { id: 'c1', accion: 'a1' },
      locals: { user: { id: 'u', name: 'Ana' } }, fetch
    }));
    expect(r.status).toBe(502);
    expect(JSON.stringify(await r.json())).not.toMatch(/10\.0\.0\.5/);
  });
});
