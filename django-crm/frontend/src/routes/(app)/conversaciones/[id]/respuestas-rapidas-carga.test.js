import { describe, it, expect, vi } from 'vitest';

/**
 * Las respuestas rápidas llegan al compositor (11/11/2026). El motor las
 * agrega a la respuesta del hilo (GET /conversaciones/<id>/mensajes) y esta
 * carga tiene que pasarlas a la página: si las deja caer, Ajustes las muestra
 * guardadas y el «/» no abre nada, con el backend en verde. Es el salto que
 * se perdió con `requiere_noc` el 29/09/2026.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: () => '' }));
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicket: async () => null,
  getTicketFormOptions: async () => ({ owners: [] }),
  updateTicket: async () => ({})
}));
vi.mock('$lib/server/v2/operadores.js', () => ({
  operadoresDeLaOrg: async () => [],
  rolDeSesion: () => 'USER'
}));

const { load } = await import('./+page.server.js');

const RR = [
  { atajo: 'saludo', texto: 'Hola {nombre}, ¿en qué te ayudo?' },
  { atajo: 'reinicio', texto: 'Desconectá el equipo 30 segundos.' }
];

const motor = (/** @type {any} */ extraMensajes) =>
  vi.fn(async (/** @type {string} */ url) => {
    const ruta = new URL(url).pathname.split('/').pop();
    const cuerpo =
      ruta === 'mensajes' ? { conversacion: { id: 'c1' }, mensajes: [], ...extraMensajes } : {};
    return new Response(JSON.stringify(cuerpo), { status: 200 });
  });

const evento = (/** @type {any} */ fetch) =>
  /** @type {any} */ ({
    fetch,
    cookies: {},
    params: { id: 'c1' },
    locals: { user: { id: 'u1', name: 'Quien Mira' } },
    depends: () => {}
  });

describe('las respuestas rápidas en la carga de la conversación', () => {
  it('EL EFECTO: llegan a la página tal como las mandó el motor', async () => {
    const datos = /** @type {any} */ (await load(evento(motor({ respuestas_rapidas: RR }))));
    expect(datos.respuestas_rapidas).toEqual(RR);
  });

  it('no agregan una ida al motor: viajan en la respuesta del hilo', async () => {
    const f = motor({ respuestas_rapidas: RR });
    await load(evento(f));
    const rutas = f.mock.calls.map(([u]) => new URL(String(u)).pathname);
    expect(rutas.some((r) => r.includes('respuestas'))).toBe(false);
  });

  it('un motor viejo que no las manda deja la lista vacía, no rompe', async () => {
    const datos = /** @type {any} */ (await load(evento(motor({}))));
    expect(datos.respuestas_rapidas).toEqual([]);
  });
});
