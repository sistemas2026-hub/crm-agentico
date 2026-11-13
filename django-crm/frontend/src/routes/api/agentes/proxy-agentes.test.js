/**
 * Crear y editar un agente: el salto del CRM al motor (04/11/2026, auditoria
 * B1). El motor exige quien lo hace y que sea ADMIN; si este proxy no lo
 * manda, crear un agente falla siempre con el backend en verde -- el salto
 * que CLAUDE.md §6 dice que ninguna prueba de backend ve. Y el autor sale de
 * la SESION, despues del cuerpo: el navegador no lo puede pisar.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'rapilink' }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));

const { POST } = await import('./+server.js');
const { PUT } = await import('./[nombre]/+server.js');

/** @type {{ url: string, cuerpo: any }[]} */
let pedidos = [];
/** @type {any} */
const fetchFalso = async (/** @type {string} */ url, /** @type {any} */ init) => {
  pedidos.push({ url, cuerpo: JSON.parse(init.body) });
  return new Response(JSON.stringify({ agente: {} }), { status: 200 });
};

const locals = (rol = 'ADMIN') => ({
  user: { id: '7c9e6679-7425-40de-944b-e07fc1f90ae7', name: 'Ana Perez', email: 'ana@x' },
  profile: { role: rol }
});
const pedido = (/** @type {any} */ cuerpo) =>
  new Request('http://crm/api/agentes', { method: 'POST', body: JSON.stringify(cuerpo) });

beforeEach(() => { pedidos = []; });

describe('crear y editar un agente llevan quien lo hace, de la sesion', () => {
  it('POST: autor y rol de la sesion, aunque el cuerpo traiga otros', async () => {
    const r = await POST(/** @type {any} */ ({
      request: pedido({ nombre: 'nuevo', autor: 'Otro', autor_rol: 'ADMIN', autor_usuario_id: 'x' }),
      locals: locals(), fetch: fetchFalso
    }));
    expect(r.status).toBe(201);
    expect(pedidos[0].url).toBe('http://motor/agentes');
    expect(pedidos[0].cuerpo).toMatchObject({
      nombre: 'nuevo', tenant: 'rapilink', autor: 'Ana Perez', autor_rol: 'ADMIN',
      autor_usuario_id: '7c9e6679-7425-40de-944b-e07fc1f90ae7'
    });
  });

  it('PUT: lo mismo al editar', async () => {
    await PUT(/** @type {any} */ ({
      params: { nombre: 'nuevo' }, request: pedido({ descripcion: 'x', autor_rol: 'ADMIN' }),
      locals: locals(), fetch: fetchFalso
    }));
    expect(pedidos[0].url).toBe('http://motor/agentes/nuevo');
    expect(pedidos[0].cuerpo).toMatchObject({ autor: 'Ana Perez', autor_rol: 'ADMIN' });
  });

  it('quien no es ADMIN no llega al motor', async () => {
    const r = await POST(/** @type {any} */ ({
      request: pedido({ nombre: 'nuevo', autor_rol: 'ADMIN' }), locals: locals('USER'), fetch: fetchFalso
    }));
    expect(r.status).toBe(403);
    expect(pedidos).toEqual([]);
  });
});
