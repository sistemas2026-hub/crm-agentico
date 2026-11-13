import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LA PALETA ⌘K LLEGA A LO QUE TRABAJA UN ISP  --  12/11/2026
 *
 * Atraviesa `search()` con el CRM (apiRequest) y el motor (fetch) doblados, y
 * afirma sobre lo que recibe la paleta: qué grupos, a dónde lleva cada uno, y
 * qué pasa cuando una fuente no contesta.
 */
vi.mock('$env/dynamic/private', () => ({ env: {} }));
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
const destino = vi.hoisted(() => ({ valor: /** @type {any} */ (null) }));
vi.mock('./tenant.js', () => ({ destinoDelAsistente: async () => destino.valor }));
vi.mock('./motor-headers.js', () => ({ headersMotor: () => ({}) }));

const { search, PLAZO_FUENTE_MS } = await import('./search.js');
const { accionesDePaleta } = await import('$lib/v2/paleta.js');

const cookies = /** @type {any} */ ({ get: () => undefined });
const crm = {
  results: [
    { type: 'ticket', id: 't1', title: 'Sin internet', subtitle: 'New' },
    { type: 'solicitud', id: 's1', title: 'Quiteria Rivera', subtitle: 'Enviada · Centro', estado: 'enviada' },
    { type: 'orden', id: 'o1', title: 'OT-12 · Teodomiro Paz', subtitle: 'Asignada', id_servicio: 'SV-778' },
    { type: 'orden', id: 'o2', title: 'OT-13 · Teodomiro Paz', subtitle: 'Cerrada', id_servicio: 'SV-778' }
  ]
};
const motor = {
  resultados: [
    { conversation_id: 'c1', nombre_cliente: 'Teodomiro', fragmento: '…el poste caído…' },
    { conversation_id: 'c1', nombre_cliente: 'Teodomiro', fragmento: 'otro mensaje' },
    { conversation_id: 'c2', nombre_cliente: null, usuario_externo: '57300', fragmento: 'poste' }
  ],
  tope: 30
};

/** @param {(url: string) => any} responder */
function ev(responder) {
  const pedidas = /** @type {string[]} */ ([]);
  return {
    pedidas,
    e: /** @type {any} */ ({
      cookies,
      locals: { org: { id: 'org-a' } },
      fetch: async (/** @type {string} */ url) => {
        pedidas.push(String(url));
        const r = responder(String(url));
        if (r instanceof Error) throw r;
        return { ok: true, status: 200, json: async () => r };
      }
    })
  };
}

beforeEach(() => {
  apiRequest.mockReset();
  destino.valor = { baseUrl: 'http://motor', tenant: 'demo' };
});

describe('⌘K', () => {
  it('trae conversaciones, solicitudes, órdenes y su cliente, cada una a su pantalla', async () => {
    apiRequest.mockResolvedValue(crm);
    const { e, pedidas } = ev(() => motor);
    const r = await search(e, 'poste');
    const por = (/** @type {string} */ kind) => r.results.filter((x) => x.kind === kind);
    // Una fila por conversación, no por mensaje.
    expect(por('Conversaciones').map((x) => x.href)).toEqual(['/conversaciones/c1', '/conversaciones/c2']);
    expect(por('Conversaciones')[1].title).toBe('57300');
    expect(por('Instalaciones')[0].href).toBe('/instalaciones?estado=enviada');
    expect(por('Órdenes').map((x) => x.href)).toEqual(['/ordenes/o1', '/ordenes/o2']);
    // El cliente una sola vez, aunque tenga dos órdenes.
    expect(por('Clientes')).toEqual([
      expect.objectContaining({ href: '/clientes/SV-778', title: 'Teodomiro Paz' })
    ]);
    expect(por('Tickets')[0].href).toBe('/tickets/t1');
    // Ids únicos: la paleta los usa como clave de cada fila.
    expect(new Set(r.results.map((x) => x.id)).size).toBe(r.results.length);
    expect(r.incompletas).toEqual([]);
    // El tenant sale de la sesión y se buscan solo los canales reales.
    expect(pedidas[0]).toContain('tenant=demo');
    expect(pedidas[0]).toContain('vista=operativo');
  });

  it('con el motor caído llega lo del CRM y se dice qué faltó', async () => {
    apiRequest.mockResolvedValue(crm);
    const { e } = ev(() => new Error('ECONNREFUSED'));
    const r = await search(e, 'poste');
    expect(r.results.some((x) => x.kind === 'Tickets')).toBe(true);
    expect(r.results.some((x) => x.kind === 'Conversaciones')).toBe(false);
    expect(r.incompletas).toEqual(['las conversaciones']);
  });

  it('con el CRM colgado no se espera más que el plazo, y llegan las conversaciones', async () => {
    vi.useFakeTimers();
    try {
      apiRequest.mockReturnValue(new Promise(() => {}));
      const { e } = ev(() => motor);
      const p = search(e, 'poste');
      await vi.advanceTimersByTimeAsync(PLAZO_FUENTE_MS + 10);
      const r = await p;
      expect(r.results.map((x) => x.kind)).toEqual(['Conversaciones', 'Conversaciones']);
      expect(r.incompletas).toEqual(['el CRM']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('sin empresa resuelta no se le pregunta nada al motor', async () => {
    apiRequest.mockResolvedValue({ results: [] });
    destino.valor = null;
    const { e, pedidas } = ev(() => motor);
    const r = await search(e, 'poste');
    expect(pedidas).toEqual([]);
    expect(r.incompletas).toEqual(['las conversaciones']);
  });

  it('con dos letras busca solo en el CRM (el motor pide tres)', async () => {
    apiRequest.mockResolvedValue({ results: [] });
    const { e, pedidas } = ev(() => motor);
    await search(e, 'po');
    expect(pedidas).toEqual([]);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });
});

describe('acciones de la paleta', () => {
  const hrefs = (/** @type {any} */ c) => accionesDePaleta(c).map((a) => a.href);

  it('llevan a las pantallas de Dexter', () => {
    expect(hrefs({ role: 'ADMIN' })).toEqual(
      expect.arrayContaining(['/conversaciones', '/supervisor-noc', '/instalaciones', '/agentes'])
    );
  });

  it('el Supervisor NOC no se le ofrece a un USER, y un módulo oculto tampoco', () => {
    expect(hrefs({ role: 'USER' })).not.toContain('/supervisor-noc');
    expect(hrefs({ role: 'ADMIN', ocultos: ['invoices'] })).not.toContain('/invoices');
    expect(hrefs({ role: 'ADMIN', ocultos: [] })).toContain('/invoices');
  });
});
