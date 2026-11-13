import { describe, it, expect, vi, beforeEach } from 'vitest';
import { debeMarcarLeida } from '$lib/conversaciones/lectura.js';

/**
 * «Leída»: el salto proxy → pantalla (11/11/2026, auditoría H4).
 *
 * Este proxy AGREGA un campo que el motor no manda -- `marcada_en`, el sello
 * de este servidor -- y la pantalla de la conversación
 * (routes/(app)/conversaciones/[id]/+page.svelte, `intentarMarcarLeida`) lo
 * lee para decidir si una cola vieja le sigue pidiendo marcar. Un campo que
 * nace en una capa intermedia es justo el que se pierde sin que ninguna
 * prueba de backend lo vea (CLAUDE.md §6: el 29/09/2026 `requiere_noc` se
 * caía en esta capa con todo en verde). Lo que se afirma acá:
 *
 *   - el cuerpo EXACTO que llega al motor (tenant de la sesión, booleano);
 *   - que la respuesta ok trae lo del motor MÁS `marcada_en`, y que ese sello
 *     es lo que la pantalla usa: pasado por el mismo `Date.parse` y
 *     `debeMarcarLeida`, una cola leída antes no vuelve a marcar y una
 *     posterior con no leídos sí;
 *   - que un error del motor vuelve con su estado y SIN sello, y que el motor
 *     caído es un 502.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => ({ ...h, 'X-Servicio': 's' }) }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa-de-la-sesion' }));

const { POST } = await import('./+server.js');

/** Lo que devuelve el motor a una marca aplicada (api.py::conversaciones_leida). */
const DEL_MOTOR = {
  leida: true,
  conversaciones: ['c1', 'c2'],
  leida_hasta: '2026-11-11T15:00:00.123+00:00'
};

/** @type {ReturnType<typeof vi.fn>} */
let fetchMock;
beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify(DEL_MOTOR), { status: 200 }));
});

/** @param {any} cuerpo @param {any} [user] */
const llamar = (cuerpo, user = { id: 'u-ana' }) =>
  POST(/** @type {any} */ ({
    request: { json: async () => cuerpo },
    params: { id: 'c1' },
    locals: { user, tenant: 'otra-empresa' },
    fetch: fetchMock
  }));

describe('POST /api/conversaciones/[id]/leida → motor', () => {
  it('manda al motor exactamente {tenant de la sesión, leida}, como JSON y por POST', async () => {
    await llamar({ leida: true, tenant: 'impostora', autor: 'x' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = /** @type {any} */ (fetchMock.mock.calls[0]);
    expect(url).toBe('http://motor/conversaciones/c1/leida');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(init.headers['X-Servicio']).toBe('s');
    expect(JSON.parse(init.body)).toEqual({ tenant: 'empresa-de-la-sesion', leida: true });
  });
});

describe('la respuesta ok, y lo que la pantalla hace con ella', () => {
  it('EL EFECTO: llega lo del motor intacto MÁS `marcada_en`, con la hora de este servidor', async () => {
    const antes = Date.now();
    const r = await llamar({ leida: true });
    const despues = Date.now();
    expect(r.status).toBe(200);
    const datos = await r.json();
    const { marcada_en, ...resto } = datos;
    expect(resto).toEqual(DEL_MOTOR);
    expect(typeof marcada_en).toBe('string');
    const sello = Date.parse(marcada_en);
    expect(sello).toBeGreaterThanOrEqual(antes);
    expect(sello).toBeLessThanOrEqual(despues);
  });

  it('el sello, leído como lo lee la pantalla, decide si una cola vieja vuelve a marcar', async () => {
    const r = await llamar({ leida: true });
    const datos = await r.json();
    // +page.svelte: lectura.marcadaEn = datos.marcada_en ? Date.parse(datos.marcada_en) : null
    const marcadaEn = datos.marcada_en ? Date.parse(datos.marcada_en) : null;
    expect(marcadaEn).not.toBeNull();
    const estado = {
      visible: true,
      enVuelo: false,
      marcadaAlAbrir: true,
      marcadaEn,
      ultimoCliente: 1000,
      marcadoHasta: 1000,
      noLeidosEnCola: 3
    };
    // Una cola leída ANTES de la marca todavía dice «3»: no se vuelve a marcar.
    expect(debeMarcarLeida({ ...estado, colaLeidaEn: /** @type {number} */ (marcadaEn) - 1 })).toBe(false);
    // Una leída DESPUÉS que sigue diciendo «3» trae algo nuevo: se marca.
    expect(debeMarcarLeida({ ...estado, colaLeidaEn: /** @type {number} */ (marcadaEn) + 1 })).toBe(true);
  });
});

describe('cuando el motor no aplica la marca', () => {
  it('un error del motor vuelve con su estado y su texto, y SIN sello', async () => {
    fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ error: 'No se pudo marcar la conversación.' }), { status: 500 }));
    const r = await llamar({ leida: true });
    expect(r.status).toBe(500);
    const datos = await r.json();
    expect(datos.error).toBe('No se pudo marcar la conversación.');
    expect(datos.marcada_en).toBeUndefined();
  });

  it('una respuesta que no es JSON tampoco se sella', async () => {
    fetchMock = vi.fn(async () => new Response('<html>502</html>', { status: 502 }));
    const r = await llamar({ leida: true });
    expect(r.status).toBe(502);
    expect((await r.json()).marcada_en).toBeUndefined();
  });

  it('el motor caído es un 502 con texto, sin sello', async () => {
    fetchMock = vi.fn(async () => {
      throw new TypeError('fetch failed');
    });
    const r = await llamar({ leida: true });
    expect(r.status).toBe(502);
    const datos = await r.json();
    expect(datos.error).toBeTruthy();
    expect(datos.marcada_en).toBeUndefined();
  });
});
