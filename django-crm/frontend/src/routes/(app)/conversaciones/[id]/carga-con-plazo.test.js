import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

/**
 * LA CONVERSACIÓN NO ESPERA A LO LENTO  --  07/11/2026
 *
 * "¿Por qué queda cargando la página de conversación?" SvelteKit no cambia de
 * pantalla hasta que este load termina, y el load esperaba doce lecturas sin
 * plazo: la ficha del cliente sale en vivo al sistema del ISP, la óptica al
 * de las OLT, el ticket al CRM. Se afirma el EFECTO, en dos partes:
 *
 *  - lo lento NO se espera: con la ficha, la óptica y el CRM colgados para
 *    siempre, el load termina sin que el reloj avance un milisegundo;
 *  - y lo lento tampoco cuelga para siempre: su promesa llega, dentro de su
 *    plazo, con el aviso de "no contestó" que el panel ya sabe leer, y deja
 *    dicho en el log cuál fue -- sin el identificador de la conversación.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: () => '' }));
const { crm } = vi.hoisted(() => ({
  crm: { ticket: /** @type {any} */ (null), operadores: /** @type {any} */ (null) }
}));
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicket: () => crm.ticket(),
  getTicketFormOptions: async () => ({ owners: [{ id: 'o1' }] }),
  updateTicket: async () => ({})
}));
vi.mock('$lib/server/v2/operadores.js', () => ({
  operadoresDeLaOrg: () => crm.operadores(),
  rolDeSesion: () => 'ADMIN'
}));

const { load } = await import('./+page.server.js');

// Los mismos valores que la carga (un +page.server.js no puede exportarlos).
// Si la carga los sube, estas pruebas lo notan: la promesa no habría llegado
// al avanzar el reloj hasta acá.
const PLAZO_MOTOR_MS = 10000;
const PLAZO_EXTERNO_MS = 10000;
const PLAZO_CRM_MS = 5000;

const ID = 'conv-con-identificador-unico';
const nunca = () => new Promise(() => {});
const json = (/** @type {any} */ cuerpo, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(cuerpo), { status }));

/** El motor contesta todo al toque, salvo las rutas de `colgadas`. Respeta la
 *  señal de abortar, como el fetch de verdad. */
const motor = (/** @type {string[]} */ colgadas = [], conversacion = {}) =>
  vi.fn((/** @type {string} */ url, /** @type {any} */ init) => {
    const ruta = new URL(url).pathname.split('/').pop();
    if (colgadas.includes(/** @type {string} */ (ruta))) {
      return new Promise((_, rechazar) => {
        init?.signal?.addEventListener('abort', () => rechazar(new DOMException('abortado', 'AbortError')));
      });
    }
    switch (ruta) {
      case 'mensajes':
        return json({ conversacion: { id: ID, ...conversacion }, mensajes: [{ id: 'm1' }] });
      case 'cliente':
        return json({ disponible: true, motivo: null, cliente: { nombre: 'Ana' } });
      case 'relevo':
        return json({ eventos: [{ tipo: 'cerrada' }] });
      case 'optica':
        return json({ disponible: true, motivo: null, optica: { rx: -20 } });
      default:
        return json({});
    }
  });

const evento = (/** @type {any} */ fetch) => /** @type {any} */ ({
  fetch,
  cookies: {},
  params: { id: ID },
  locals: { user: { id: 'u1', name: 'Quien Mira' } },
  depends: () => {}
});

/** El load terminó sin que el reloj avanzara: no esperó nada colgado. Con
 *  temporizadores falsos, un load que esperara no terminaría nunca. */
const terminaSinEsperar = async (/** @type {Promise<any>} */ promesa) => {
  let listo = false;
  promesa.then(() => (listo = true), () => (listo = true));
  await vi.advanceTimersByTimeAsync(0);
  expect(listo).toBe(true);
  return /** @type {any} */ (await promesa);
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  crm.ticket = async () => ({ ticket: { id: 'k1', assignee_id: 'o1' } });
  crm.operadores = async () => [];
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('la conversación se abre sin esperar a lo lento', () => {
  it('EL EFECTO: con la ficha, la óptica y el CRM colgados, el load termina igual', async () => {
    crm.ticket = nunca;
    crm.operadores = nunca;
    const datos = await terminaSinEsperar(
      load(evento(motor(['cliente', 'cuenta', 'optica'], { escalada_a_humano: true, caso_id: 'k1' })))
    );
    expect(datos.mensajes).toEqual([{ id: 'm1' }]);
    expect(datos.relevo).toEqual([{ tipo: 'cerrada' }]);
    // Viajan aparte; la pantalla los recibe cuando lleguen.
    expect(datos.fichaCliente).toBeInstanceOf(Promise);
    expect(datos.cuenta).toBeInstanceOf(Promise);
    expect(datos.optica).toBeInstanceOf(Promise);
    expect(datos.caso).toBeInstanceOf(Promise);
    expect(datos.operadores).toBeInstanceOf(Promise);
  });

  it('lo que no hace falta pedir viaja plano, no como promesa', async () => {
    const datos = await terminaSinEsperar(load(evento(motor())));
    expect(datos.optica).toEqual({ disponible: false, motivo: 'no_consultada', optica: null });
    expect(datos.caso).toBeNull();
    expect(datos.owners).toEqual([]);
  });
});

describe('y lo lento tampoco cuelga para siempre', () => {
  it('la ficha colgada llega como «sin respuesta» al vencer su plazo, y lo dice el log', async () => {
    const datos = await terminaSinEsperar(load(evento(motor(['cliente']))));
    await vi.advanceTimersByTimeAsync(PLAZO_EXTERNO_MS + 10);
    expect(await datos.fichaCliente).toEqual({ disponible: false, motivo: 'sin_respuesta', cliente: null });
    // Cuál fue y por qué, para saber cuál sistema es el lento sin adivinar.
    expect(console.warn).toHaveBeenCalledWith(expect.stringMatching(/conversacion cliente.*plazo/));
    // Y nunca el identificador de la conversación: la URL no va al log.
    for (const [linea] of /** @type {any} */ (console.warn).mock.calls) {
      expect(String(linea)).not.toContain(ID);
    }
  });

  it('la cuenta colgada llega como «sin respuesta», nunca como «al día»', async () => {
    const datos = await terminaSinEsperar(load(evento(motor(['cuenta']))));
    await vi.advanceTimersByTimeAsync(PLAZO_EXTERNO_MS + 10);
    expect(await datos.cuenta).toEqual({ disponible: false, motivo: 'sin_respuesta' });
  });

  it('la óptica colgada de una escalada llega sin medición', async () => {
    const datos = await terminaSinEsperar(load(evento(motor(['optica'], { escalada_a_humano: true }))));
    await vi.advanceTimersByTimeAsync(PLAZO_EXTERNO_MS + 10);
    expect((await datos.optica).disponible).toBe(false);
  });

  it('el CRM colgado: sin ticket y sin operadores, nunca «cargando» para siempre', async () => {
    crm.ticket = nunca;
    crm.operadores = nunca;
    const datos = await terminaSinEsperar(load(evento(motor([], { caso_id: 'k1' }))));
    await vi.advanceTimersByTimeAsync(PLAZO_CRM_MS + 10);
    expect(await datos.caso).toBeNull();
    expect(await datos.owners).toEqual([]);
    expect(await datos.operadores).toEqual([]);
  });
});

describe('lo que sí se espera, con plazo', () => {
  it('un panel del motor colgado se queda vacío; el hilo llega', async () => {
    const promesa = load(evento(motor(['herramientas', 'hilo'])));
    await vi.advanceTimersByTimeAsync(PLAZO_MOTOR_MS + 10);
    const datos = /** @type {any} */ (await promesa);
    expect(datos.mensajes).toEqual([{ id: 'm1' }]);
    expect(datos.herramientas).toEqual([]);
    expect(datos.chat.agrupa).toBe(false);
  });

  it('el hilo colgado no espera sin fin: dice que el asistente tarda', async () => {
    const resultado = load(evento(motor(['mensajes']))).then(() => null, (/** @type {any} */ e) => e);
    await vi.advanceTimersByTimeAsync(PLAZO_MOTOR_MS + 10);
    const e = await resultado;
    expect(e?.status).toBe(503);
    expect(e?.body?.message).toMatch(/tardando/);
  });
});

describe('con todo al día', () => {
  it('llega todo, y una conversación que no existe sigue siendo 404', async () => {
    crm.operadores = async () => [{ usuario_id: 'u2', nombre: 'Otra' }];
    const datos = await terminaSinEsperar(
      load(evento(motor([], { caso_id: 'k1', escalada_a_humano: true })))
    );
    expect((await datos.fichaCliente).cliente).toEqual({ nombre: 'Ana' });
    expect((await datos.optica).optica).toEqual({ rx: -20 });
    expect(await datos.caso).toEqual({ id: 'k1', assignee_id: 'o1' });
    expect(await datos.owners).toEqual([{ id: 'o1' }]);
    expect(await datos.operadores).toEqual([{ usuario_id: 'u2', nombre: 'Otra' }]);

    const no = vi.fn(() => json({ error: 'x' }, 404));
    const e = await load(evento(no)).then(() => null, (/** @type {any} */ x) => x);
    expect(e?.status).toBe(404);
  });
});
