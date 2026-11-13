import { describe, it, expect, vi } from 'vitest';

/**
 * La cola de Conversaciones pide al motor solo las cerradas recientes.
 *
 * La consulta del motor paga por conversacion y el layout la repite cada 8 s:
 * sin tope, el costo crecia con todo el historial de la empresa. Lo que se
 * afirma es el EFECTO: la URL que sale al motor lleva `cerradas_dias`, y la
 * pantalla recibe el numero que el motor contesto (para decir "ultimos N dias").
 */
const { envMock } = vi.hoisted(() => ({ envMock: { PRIVATE_ASISTENTE_URL: 'http://motor:5000' } }));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { load } = await import('./+layout.server.js');

describe('la cola de Conversaciones', () => {
  it('pide al motor solo las cerradas de los ultimos 30 dias', async () => {
    const urls = /** @type {string[]} */ ([]);
    const fetch = vi.fn(async (/** @type {string} */ url) => {
      urls.push(url);
      return { ok: true, json: async () => ({ conversaciones: [], cerradas_dias: 30 }) };
    });
    const datos = /** @type {any} */ (await load(/** @type {any} */ ({
      fetch, depends: () => {}, locals: { tenant: 'rapilink', user: { id: '1', name: 'Ana' } }
    })));
    expect(urls).toHaveLength(1);
    expect(urls[0]).toContain('cerradas_dias=30');
    expect(urls[0]).toContain('por_numero=1');
    expect(datos.cerradas_dias).toBe(30);
  });

  /* 11/11/2026: no leídos y etiquetas del equipo. CLAUDE.md §6 cuenta dos
     veces que un dato viajaba bien desde el motor y la capa servidor lo
     dejaba caer. Acá: el catálogo es un campo NUEVO de la respuesta, y sin él
     las filas llegan con sus claves y ninguna se dibuja. */
  it('el catálogo de etiquetas y los no leídos de cada fila llegan a la pantalla', async () => {
    const catalogo = [{ clave: 'vip', nombre: 'Cliente VIP', color: 'violeta' }];
    const fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        conversaciones: [{ id: 'c1', no_leidos: 3, etiquetas_del_equipo: ['vip'] }],
        etiquetas_del_equipo: catalogo
      })
    }));
    const datos = /** @type {any} */ (await load(/** @type {any} */ ({
      fetch, depends: () => {}, locals: { tenant: 'rapilink', user: { id: '1', name: 'Ana' } }
    })));
    expect(datos.etiquetas_del_equipo).toEqual(catalogo);
    expect(datos.conversaciones[0]).toMatchObject({ no_leidos: 3, etiquetas_del_equipo: ['vip'] });
  });

  it('un motor sin catálogo (versión vieja) deja una lista vacía, no undefined', async () => {
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ conversaciones: [] }) }));
    const datos = /** @type {any} */ (await load(/** @type {any} */ ({
      fetch, depends: () => {}, locals: { tenant: 'rapilink', user: { id: '1', name: 'Ana' } }
    })));
    expect(datos.etiquetas_del_equipo).toEqual([]);
  });
});
