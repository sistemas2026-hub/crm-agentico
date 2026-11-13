import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * UNA SOLA IDA AL MOTOR POR APERTURA  --  11/11/2026
 *
 * Abrir una conversación disparaba ocho lecturas en paralelo contra un motor
 * de un proceso y 16 hilos que además atiende WhatsApp. Ahora el hilo y sus
 * siete paneles vienen juntos en GET .../apertura. Lo que se afirma, sobre el
 * EFECTO:
 *
 *  - por apertura sale UNA lectura de la base del motor, no ocho;
 *  - lo que el load devuelve a la página es IDÉNTICO a lo que devolvía con
 *    las ocho (la página no se tocó: cualquier clave que cambie de lugar se
 *    pierde en silencio, como `requiere_noc` el 29/09/2026);
 *  - con un motor que todavía no tiene la ruta (404 sin código) se vuelve a
 *    las ocho y la conversación se abre igual; con un 404 que sí dice
 *    «no existe» es 404 y NO se vuelve a pedir nada.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: () => '' }));
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicket: async () => ({ ticket: { id: 'k1' } }),
  getTicketFormOptions: async () => ({ owners: [{ id: 'o1' }] }),
  updateTicket: async () => ({})
}));
vi.mock('$lib/server/v2/operadores.js', () => ({
  operadoresDeLaOrg: async () => [{ usuario_id: 'u2', nombre: 'Otra' }],
  rolDeSesion: () => 'ADMIN'
}));
// Quién mira (12/11/2026): la lista de la organización, para el perfil.
vi.mock('$lib/server/v2/org-people.js', () => ({
  getOrgPeopleAndTeams: async () => ({ people: [], teams: [] }),
  resolveMe: () => null
}));

const { load } = await import('./+page.server.js');

const ID = 'conv-apertura-unica';

/** Lo que responde cada ruta individual del motor; /apertura las junta. */
const CUERPOS = {
  mensajes: {
    conversacion: { id: ID, escalada_a_humano: true, caso_id: 'k1' },
    mensajes: [{ id: 'm1', rol: 'user' }],
    respuestas_rapidas: [{ atajo: 'saludo', texto: 'Hola {nombre}' }]
  },
  hilo: { tramos: [{ id: 't0' }], hay_anteriores: true, antes: 't0', mas_reciente_id: ID,
          abiertas: [], posteriores: [], agrupa: true, total_tramos: 2 },
  herramientas: { herramientas: [{ nombre: 'consultar', exito: true }],
                  diagnostico: { normales: 1, bloqueadas: 0, errores: 0 } },
  relevo: { eventos: [{ tipo: 'escalada', nuevo_estado: 'humano' }] },
  equipo: { acciones: [{ id: 'e1', veredicto: 'confirmada' }] },
  sincronizaciones: { sincronizaciones: [{ id: 's1', estado: 'pendiente' }] },
  acciones: { acciones: [{ id: 'a1', estado: 'vencida' }] },
  casos: { casos: ['instalacion'], rotulos: { instalacion: 'Instalación' } }
};
const EXTERNAS = ['cliente', 'cuenta', 'optica'];

const json = (/** @type {any} */ cuerpo, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(cuerpo), { status }));
/** El nombre de la ruta: el último tramo, salvo /manual/casos que es «casos». */
const rutaDe = (/** @type {any} */ url) => /** @type {string} */ (new URL(String(url)).pathname.split('/').pop());

/** Un motor que ya tiene /apertura. `cambios` pisa claves de la apertura (un
 *  panel en null, por ejemplo). Las ocho rutas individuales también contestan,
 *  para poder contar si alguien las pidió sin necesidad. */
const motorNuevo = (/** @type {Record<string, any>} */ cambios = {}) =>
  vi.fn((/** @type {string} */ url) => {
    const r = rutaDe(url);
    if (r === 'apertura') return json({ apertura: true, ...CUERPOS, ...cambios });
    if (EXTERNAS.includes(r)) return json({ disponible: false, motivo: 'prueba' });
    return json(/** @type {any} */ (CUERPOS)[r] ?? {});
  });

/** Un motor viejo: Flask contesta 404 sin JSON a la ruta que no conoce. */
const motorViejo = () =>
  vi.fn((/** @type {string} */ url) => {
    const r = rutaDe(url);
    if (r === 'apertura') return Promise.resolve(new Response('<h1>Not Found</h1>', { status: 404 }));
    if (EXTERNAS.includes(r)) return json({ disponible: false, motivo: 'prueba' });
    return json(/** @type {any} */ (CUERPOS)[r] ?? {});
  });

/** Las rutas de la base del motor que se pidieron (sin las externas, que
 *  viajan como promesas y no son parte de esto). */
const lecturasDelMotor = (/** @type {any} */ f) =>
  f.mock.calls.map((/** @type {any[]} */ [u]) => rutaDe(u)).filter((/** @type {string} */ r) => !EXTERNAS.includes(r));

const evento = (/** @type {any} */ fetch) => /** @type {any} */ ({
  fetch, cookies: {}, params: { id: ID },
  locals: { user: { id: 'u1', name: 'Quien Mira' } }, depends: () => {}
});

/** El resultado del load con sus promesas resueltas, para comparar entero. */
const resuelto = async (/** @type {Record<string, any>} */ datos) =>
  Object.fromEntries(await Promise.all(Object.entries(datos).map(async ([k, v]) => [k, await v])));

const OCHO = ['mensajes', 'herramientas', 'casos', 'relevo', 'equipo', 'sincronizaciones', 'acciones', 'hilo'];

beforeEach(() => { vi.spyOn(console, 'warn').mockImplementation(() => {}); });
afterEach(() => { vi.restoreAllMocks(); });

describe('una sola ida al motor por apertura', () => {
  it('EL EFECTO: de la base del motor se pide /apertura y nada más', async () => {
    const f = motorNuevo();
    await load(evento(f));
    expect(lecturasDelMotor(f)).toEqual(['apertura']);
  });

  it('cada clave de la apertura llega a la misma variable que antes', async () => {
    const datos = /** @type {any} */ (await load(evento(motorNuevo())));
    expect(datos.conversacion).toEqual(CUERPOS.mensajes.conversacion);
    expect(datos.mensajes).toEqual(CUERPOS.mensajes.mensajes);
    expect(datos.respuestas_rapidas).toEqual(CUERPOS.mensajes.respuestas_rapidas);
    expect(datos.chat).toEqual(CUERPOS.hilo);
    expect(datos.herramientas).toEqual(CUERPOS.herramientas.herramientas);
    expect(datos.diagnostico).toEqual(CUERPOS.herramientas.diagnostico);
    expect(datos.relevo).toEqual(CUERPOS.relevo.eventos);
    expect(datos.equipo).toEqual(CUERPOS.equipo.acciones);
    expect(datos.sincronizaciones).toEqual(CUERPOS.sincronizaciones.sincronizaciones);
    expect(datos.acciones).toEqual(CUERPOS.acciones.acciones);
    expect(datos.casos).toEqual(CUERPOS.casos.casos);
  });

  it('la forma devuelta es idéntica a la de las ocho lecturas, clave por clave y en el mismo orden', async () => {
    const conUna = /** @type {any} */ (await load(evento(motorNuevo())));
    const conOcho = /** @type {any} */ (await load(evento(motorViejo())));
    expect(Object.keys(conUna)).toEqual(Object.keys(conOcho));
    expect(await resuelto(conUna)).toEqual(await resuelto(conOcho));
  });

  it('un panel que el motor mandó en null queda vacío, como cuando no contestaba', async () => {
    const datos = /** @type {any} */ (await load(evento(motorNuevo({ hilo: null, herramientas: null, casos: null }))));
    expect(datos.mensajes).toEqual(CUERPOS.mensajes.mensajes);
    expect(datos.herramientas).toEqual([]);
    expect(datos.diagnostico).toBeNull();
    expect(datos.casos).toEqual([]);
    expect(datos.chat).toEqual({ tramos: [], hay_anteriores: false, antes: null,
                                 mas_reciente_id: ID, abiertas: [], posteriores: [], agrupa: false });
  });
});

describe('mientras conviven frontend nuevo y motor viejo', () => {
  it('404 SIN código: el motor no tiene la ruta, se vuelve a las ocho y la conversación se abre', async () => {
    const f = motorViejo();
    const datos = /** @type {any} */ (await load(evento(f)));
    const pedidas = lecturasDelMotor(f);
    expect(pedidas[0]).toBe('apertura');
    expect([...pedidas.slice(1)].sort()).toEqual([...OCHO].sort());
    expect(datos.mensajes).toEqual(CUERPOS.mensajes.mensajes);
    expect(datos.chat).toEqual(CUERPOS.hilo);
  });

  it('un 200 que no es una apertura también vuelve a las ocho', async () => {
    const f = vi.fn((/** @type {string} */ url) => {
      const r = rutaDe(url);
      if (r === 'apertura') return json({});
      if (EXTERNAS.includes(r)) return json({ disponible: false });
      return json(/** @type {any} */ (CUERPOS)[r] ?? {});
    });
    const datos = /** @type {any} */ (await load(evento(f)));
    expect(lecturasDelMotor(f)).toContain('mensajes');
    expect(datos.mensajes).toEqual(CUERPOS.mensajes.mensajes);
  });

  it('404 CON código «conversacion_inexistente»: es 404, y no se vuelve a pedir nada', async () => {
    const f = vi.fn((/** @type {string} */ url) => {
      const r = rutaDe(url);
      if (r === 'apertura') return json({ error: 'no existe', codigo: 'conversacion_inexistente' }, 404);
      return json(/** @type {any} */ (CUERPOS)[r] ?? { disponible: false });
    });
    const e = await load(evento(f)).then(() => null, (/** @type {any} */ x) => x);
    expect(e?.status).toBe(404);
    expect(lecturasDelMotor(f)).toEqual(['apertura']);
  });

  it('500 en la apertura: 500 con el mensaje del motor, sin volver a las ocho', async () => {
    const f = vi.fn((/** @type {string} */ url) => {
      const r = rutaDe(url);
      if (r === 'apertura') return json({ error: 'No se pudo leer la conversacion.' }, 500);
      return json(/** @type {any} */ (CUERPOS)[r] ?? { disponible: false });
    });
    const e = await load(evento(f)).then(() => null, (/** @type {any} */ x) => x);
    expect(e?.status).toBe(500);
    expect(e?.body?.message).toBe('No se pudo leer la conversacion.');
    expect(lecturasDelMotor(f)).toEqual(['apertura']);
  });
});
