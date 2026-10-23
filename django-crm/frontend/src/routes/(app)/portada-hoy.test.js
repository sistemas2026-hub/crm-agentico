/**
 * LA PORTADA ARMA SU COLA CON LO QUE LLEGO, Y DICE LO QUE NO.
 *
 * Atraviesa la cadena del servidor: load -> leerFuentesDeHoy -> cada lector ->
 * armarCola. Los lectores de cada modulo se sustituyen; lo que corre de verdad
 * es la combinacion, que es donde un campo se cae o una falla tumba al resto.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fuentes = vi.hoisted(() => ({
  destino: /** @type {any} */ (null),
  today: /** @type {any} */ (null),
  solicitudes: /** @type {any} */ ({ solicitudes: [] }),
  bloqueos: /** @type {any} */ ({ datos: { bloqueos: [] }, error: null }),
  pedidos: /** @type {any} */ ({ filas: [], error: false })
}));

vi.mock('$lib/server/v2/tenant.js', () => ({ destinoDelAsistente: async () => fuentes.destino }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/today.js', () => ({
  getToday: async () => {
    if (!fuentes.today) throw new Error('CRM caido');
    return fuentes.today;
  }
}));
vi.mock('$lib/server/v2/solicitudes.js', () => ({ leerBandeja: async () => fuentes.solicitudes }));
vi.mock('$lib/server/v2/programacion-noc.js', () => ({ leerBloqueosAbiertos: async () => fuentes.bloqueos }));
vi.mock('$lib/server/v2/inventario.js', () => ({ leerReporte: async () => fuentes.pedidos }));

const { load } = await import('./+page.server.js');

const hace = (min) => new Date(Date.now() - min * 60000).toISOString();

/** @param {(url: string) => any} responder */
function evento(responder) {
  return /** @type {any} */ ({
    cookies: { get: () => undefined },
    locals: {},
    fetch: async (url) => {
      const r = responder(String(url));
      if (r instanceof Error) throw r;
      return { ok: true, status: 200, json: async () => r };
    }
  });
}

beforeEach(() => {
  fuentes.destino = { baseUrl: 'http://motor:5000', tenant: 'demo' };
  fuentes.today = { queue: [], summary: { count: 0, shown: 0, sources: [] }, later: [] };
  fuentes.solicitudes = { solicitudes: [] };
  fuentes.bloqueos = { datos: { bloqueos: [] }, error: null };
  fuentes.pedidos = { filas: [], error: false };
});

describe('portada Hoy', () => {
  it('con todo arriba junta motor, campo, instalaciones y CRM en una cola', async () => {
    fuentes.solicitudes = { solicitudes: [{ enviada_en: hace(120) }] };
    fuentes.bloqueos = { datos: { bloqueos: [{ requiere_noc: true, minutos_detenido: 40 }] }, error: null };
    fuentes.today = {
      queue: [{ id: 3, tone: 'rust', title: 'Factura vencida', href: '/invoices/3', due: 'Vencida' }],
      summary: { count: 1, shown: 1, sources: [] },
      later: []
    };
    const datos = /** @type {any} */ (
      await load(
        evento((url) =>
          url.includes('/conversaciones')
            ? { conversaciones: [{ id: 'c9', banda: 1, esperando_desde: hace(20) }], sla_toma_minutos: 15 }
            : { totales: { conversaciones_activas: 23, esperando_humano: 4, atendidas_hoy: 187, fallos_hoy: 2, agentes_activos: 6 }, agentes: new Array(8).fill({}) }
        )
      )
    );
    // Dentro de "necesita atencion", la que espera hace mas va primero: la
    // instalacion (120 min) antes que el bloqueo (40 min).
    expect(datos.cola.map((i) => i.id)).toEqual(['conv-espera', 'crm-3', 'instalaciones', 'noc-bloqueos']);
    expect(datos.cola[0].href).toBe('/conversaciones/c9');
    expect(datos.dexter).toMatchObject({ activas: 23, esperanPersona: 4, agentesActivos: 6, agentesTotal: 8 });
    expect(datos.noLeidas).toEqual([]);
    expect(datos.resumen).toMatch(/^4 cosas te necesitan ahora; 2 ya pasaron su plazo\./);
  });

  it('con el motor caido muestra el resto y dice que no pudo leer', async () => {
    fuentes.solicitudes = { solicitudes: [{ enviada_en: hace(30) }] };
    const datos = /** @type {any} */ (await load(evento(() => new Error('ECONNREFUSED'))));
    expect(datos.cola.map((i) => i.id)).toEqual(['instalaciones']);
    expect(datos.dexter).toBeNull();
    expect(datos.noLeidas).toEqual(['las conversaciones', 'el estado de Dexter']);
    // Sin conversaciones leidas no hay fila "Conversaciones: 0": no se sabe, no es cero.
    expect(datos.porArea.find((a) => a.id === 'conversaciones')).toBeUndefined();
  });

  it('una fuente que depende del rol y falla no se anuncia', async () => {
    fuentes.pedidos = { filas: [], error: true };
    fuentes.bloqueos = { datos: null, error: 'Sin permiso' };
    const datos = /** @type {any} */ (
      await load(evento((url) => (url.includes('/conversaciones') ? { conversaciones: [] } : { totales: {} })))
    );
    expect(datos.noLeidas).toEqual([]);
    expect(datos.porArea.map((a) => a.id)).toEqual(['conversaciones', 'instalaciones']);
  });

  it('sin empresa resuelta no se le pide nada al motor', async () => {
    fuentes.destino = null;
    const pedidas = [];
    await load(
      evento((url) => {
        pedidas.push(url);
        return {};
      })
    );
    expect(pedidas).toEqual([]);
  });
});
