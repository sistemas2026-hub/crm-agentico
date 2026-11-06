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
});
