import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * LA PAGINA DE UN AGENTE, DEL LADO DEL SERVIDOR  --  13/11/2026
 *
 * Se protege la CADENA (CLAUDE.md §6): que cada dato llegue del motor con su
 * nombre, que uno que falla no tumbe la pagina, que un agente que no existe
 * sea un 404 y no una pagina vacia, y que pausar y restaurar viajen al motor
 * solo para un ADMIN, con el tenant de la SESION.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/tenant.js', () => ({
  tenantDeLaSesion: async () => 'rapilink',
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'rapilink' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));

const { load, actions } = await import('./+page.server.js');

const AGENTE = { nombre: 'soporte', orientado_a: 'colaborador', herramientas: [] };

/** @param {Record<string, any>} respuestas ruta -> cuerpo (o 'falla') */
function motor(respuestas) {
  /** @type {{url: string, metodo: string, cuerpo: any}[]} */
  const pedidos = [];
  globalThis.fetch = /** @type {any} */ (vi.fn(async (url, opciones) => {
    const u = new URL(String(url));
    pedidos.push({ url: u.pathname, metodo: opciones?.method ?? 'GET', cuerpo: opciones?.body ? JSON.parse(opciones.body) : null });
    const r = respuestas[u.pathname];
    if (r === 'falla') return { ok: false, status: 503, json: async () => ({ error: 'caido' }) };
    if (r === undefined) return { ok: false, status: 404, json: async () => ({ error: 'no' }) };
    return { ok: true, status: 200, json: async () => r };
  }));
  return pedidos;
}

const evento = (rol = 'ADMIN', extra = {}) => ({
  params: { nombre: 'soporte' }, locals: { profile: { role: rol }, user: { name: 'Ana Pérez', id: 'u1' } },
  fetch: (/** @type {any} */ url, /** @type {any} */ op) => globalThis.fetch(url, op), ...extra
});

describe('cargar la pagina', () => {
  it('trae el agente y cada dato con el nombre del motor', async () => {
    motor({
      '/agentes': { agentes: [AGENTE] },
      '/agentes/catalogo': { herramientas: [{ nombre: 'x' }] },
      '/reportes/autonomia-ganada': { acciones: [] },
      '/reportes/agentes': { dias: 30, agentes: { soporte: { conversaciones: 5, escaladas: 1 } } },
      '/agentes/soporte/bitacora': { acciones: [{ herramienta: 'reiniciar_ont' }] },
      '/agentes/soporte/historial': { cambios: [{ version: 3 }] },
      '/habilidades/huecos': { huecos: [{ rol: 'soporte', n_casos: 2 }, { rol: 'ventas', n_casos: 1 }] }
    });
    const d = /** @type {any} */ (await load(/** @type {any} */ (evento())));
    expect(d.agente.nombre).toBe('soporte');
    expect(d.catalogo).toEqual([{ nombre: 'x' }]);
    expect(d.desempeno).toEqual({ conversaciones: 5, escaladas: 1 });
    expect(d.bitacora).toEqual([{ herramienta: 'reiniciar_ont' }]);
    expect(d.historial).toEqual([{ version: 3 }]);
    expect(d.huecos).toEqual([{ rol: 'soporte', n_casos: 2 }]);
    expect(d.esAdmin).toBe(true);
  });

  it('un dato que falla no tumba la pagina: llega null y lo demas se ve', async () => {
    motor({ '/agentes': { agentes: [AGENTE] }, '/reportes/agentes': 'falla', '/agentes/soporte/bitacora': 'falla' });
    const d = /** @type {any} */ (await load(/** @type {any} */ (evento('OPERACIONES'))));
    expect(d.agente.nombre).toBe('soporte');
    expect(d.desempeno).toBeNull();
    expect(d.bitacora).toBeNull();
    expect(d.historial).toBeNull();
    expect(d.esAdmin).toBe(false);
  });

  it('sin conversaciones no es "0": se marca sin_conversaciones', async () => {
    motor({ '/agentes': { agentes: [AGENTE] }, '/reportes/agentes': { dias: 30, agentes: {} } });
    const d = /** @type {any} */ (await load(/** @type {any} */ (evento())));
    expect(d.desempeno).toEqual({ sin_conversaciones: true });
  });

  it('un agente que no existe es un 404', async () => {
    motor({ '/agentes': { agentes: [{ nombre: 'otro' }] } });
    await expect(load(/** @type {any} */ (evento()))).rejects.toMatchObject({ status: 404 });
  });
});

describe('pausar, reanudar y restaurar', () => {
  /** @type {any[]} */
  let pedidos;
  beforeEach(() => {
    pedidos = motor({ '/agentes/soporte/pausa': { agente: AGENTE }, '/agentes/soporte/restaurar': { agente: AGENTE } });
  });

  it('pausar viaja al motor con el tenant de la sesion', async () => {
    const r = await actions.pausar(/** @type {any} */ (evento()));
    expect(r).toEqual({ pausa: { ok: 'pausado' } });
    expect(pedidos).toEqual([{ url: '/agentes/soporte/pausa', metodo: 'PUT', cuerpo: { pausado: true, autor: 'Ana Pérez', tenant: 'rapilink' } }]);
  });

  it('reanudar manda pausado: false', async () => {
    await actions.reanudar(/** @type {any} */ (evento()));
    expect(pedidos[0].cuerpo).toEqual({ pausado: false, autor: 'Ana Pérez', tenant: 'rapilink' });
  });

  it('sin ser ADMIN no viaja nada', async () => {
    const r = /** @type {any} */ (await actions.pausar(/** @type {any} */ (evento('OPERACIONES'))));
    expect(r.status).toBe(403);
    expect(pedidos).toEqual([]);
  });

  it('restaurar exige confirmar y una version que sea numero', async () => {
    const pedir = (/** @type {Record<string,string>} */ campos) => {
      const f = new FormData();
      for (const [k, v] of Object.entries(campos)) f.set(k, v);
      return actions.restaurar(/** @type {any} */ (evento('ADMIN', { request: new Request('http://crm/x', { method: 'POST', body: f }) })));
    };
    expect(/** @type {any} */ (await pedir({ version: '206' })).status).toBe(400);
    expect(/** @type {any} */ (await pedir({ version: 'abc', confirmo: 'si' })).status).toBe(400);
    expect(pedidos).toEqual([]);
    expect(await pedir({ version: '206', confirmo: 'si' })).toEqual({ restaurar: { version: 206, ok: true } });
    expect(pedidos).toEqual([{ url: '/agentes/soporte/restaurar', metodo: 'POST', cuerpo: { version: 206, autor: 'Ana Pérez', tenant: 'rapilink' } }]);
  });

  it('si el motor rechaza, se dice por que', async () => {
    motor({ '/agentes/soporte/pausa': 'falla' });
    const r = /** @type {any} */ (await actions.pausar(/** @type {any} */ (evento())));
    expect(r.status).toBe(502);
    expect(r.data.pausa.error).toBe('caido');
  });

  it('las acciones de autonomia son las mismas que en /agentes', async () => {
    const lista = await import('../+page.server.js');
    expect(actions.promover).toBe(lista.actions.promover);
    expect(actions.retirar).toBe(lista.actions.retirar);
  });
});
