import { describe, it, expect, vi } from 'vitest';

/**
 * La ficha del cliente se pide diciendo QUIÉN mira (12/11/2026).
 *
 * El motor filtra la ficha por rol y por el área del perfil
 * (nucleo/seguridad/ficha_por_area.py); sin `rol`/`perfil` entrega el defecto
 * sin cédula a todos, ADMIN incluido. Se afirma sobre la URL que sale al motor
 * y sobre que buscar el perfil no retiene la pantalla.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: () => '' }));
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicket: async () => null, getTicketFormOptions: async () => ({ owners: [] }), updateTicket: async () => ({})
}));
const sesion = vi.hoisted(() => ({ rol: 'USER', people: /** @type {any} */ (null) }));
vi.mock('$lib/server/v2/operadores.js', () => ({
  operadoresDeLaOrg: async () => [], rolDeSesion: () => sesion.rol
}));
// Solo se dobla la ida al CRM; resolveMe es la real (empareja por correo).
vi.mock('$lib/server/v2/org-people.js', async (original) => ({
  ...(/** @type {any} */ (await original())),
  getOrgPeopleAndTeams: () => sesion.people
}));

const { load } = await import('./+page.server.js');

const motor = () =>
  vi.fn((/** @type {string} */ url) => {
    const ruta = new URL(url).pathname.split('/').pop();
    const cuerpo = ruta === 'apertura'
      ? { apertura: true, mensajes: { conversacion: { id: 'c1' }, mensajes: [] },
          herramientas: { herramientas: [{ herramienta: 'consultar_cliente', exito: true,
                                           parametros: { cedula: '...4567' } }] } }
      : { disponible: true, cliente: {} };
    return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: 200 }));
  });

const evento = (/** @type {any} */ fetch) => /** @type {any} */ ({
  fetch, cookies: {}, params: { id: 'c 1' }, depends: () => {},
  locals: { user: { id: 'u1', name: 'Ana', email: 'Ana@Empresa.co' } }
});

/** La URL con la que se pidió la ficha, o undefined si no se pidió. */
const urlDeLaFicha = (/** @type {any} */ f) =>
  f.mock.calls.map((/** @type {any[]} */ [u]) => new URL(u)).find((/** @type {URL} */ u) => u.pathname.endsWith('/cliente'));

describe('la ficha se pide con rol y perfil de quien mira', () => {
  it('con perfil resuelto por correo: rol del JWT y Profile.id', async () => {
    sesion.rol = 'USER';
    sesion.people = Promise.resolve({ people: [{ id: 'p-ana', email: 'ana@empresa.co' }], teams: [] });
    const f = motor();
    const datos = /** @type {any} */ (await load(evento(f)));
    await datos.fichaCliente;
    const u = urlDeLaFicha(f);
    expect(u.pathname).toBe('/conversaciones/c%201/cliente');
    expect(Object.fromEntries(u.searchParams)).toEqual({ tenant: 'empresa', rol: 'USER', perfil: 'p-ana' });
  });

  it('sin perfil (el CRM no lo conoce o falla): rol solo, y el motor cae al defecto', async () => {
    sesion.rol = 'ADMIN';
    for (const people of [Promise.resolve({ people: [], teams: [] }), Promise.reject(new Error('caído'))]) {
      sesion.people = people;
      const f = motor();
      const datos = /** @type {any} */ (await load(evento(f)));
      expect(await datos.fichaCliente).toMatchObject({ disponible: true });
      expect(Object.fromEntries(urlDeLaFicha(f).searchParams)).toEqual({ tenant: 'empresa', rol: 'ADMIN' });
    }
  });

  it('«Proceso» recibe las llamadas SIN parámetros: ni enmascarados salen al navegador', async () => {
    sesion.rol = 'USER';
    sesion.people = Promise.resolve({ people: [], teams: [] });
    const datos = /** @type {any} */ (await load(evento(motor())));
    expect(datos.herramientas).toEqual([{ herramienta: 'consultar_cliente', exito: true }]);
    expect(JSON.stringify(datos.herramientas)).not.toMatch(/4567/);
  });

  it('buscar el perfil NO retiene la pantalla: el load vuelve con la ficha todavía en viaje', async () => {
    sesion.rol = 'USER';
    sesion.people = new Promise(() => {}); // el CRM no contesta nunca
    const f = motor();
    const datos = /** @type {any} */ (await load(evento(f)));
    expect(datos.conversacion).toEqual({ id: 'c1' });
    expect(typeof datos.fichaCliente?.then).toBe('function');
    expect(urlDeLaFicha(f)).toBeUndefined();
  });
});
