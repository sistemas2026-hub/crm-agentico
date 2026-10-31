/**
 * EL SERVIDOR DEL DETALLE DEL TICKET: dos cosas que la pantalla no puede
 * comprobar por su cuenta.
 *
 * 1. `estadoConversacion` (load): si el ticket tiene un chat al que la
 *    respuesta pueda salir. De ahi sale el aviso "Sale por WhatsApp" o "el
 *    cliente no va a recibir este mensaje". Se distinguen TRES respuestas,
 *    porque "el motor no contesto" no es "no hay chat".
 *
 * 2. ASIGNAR DESDE EL ENCABEZADO (`?/asignar`).
 *
 * Se afirma sobre el EFECTO: que le llega a `updateTicket` (el PATCH al API),
 * y que no le llega nada cuando no corresponde. Dos trampas concretas:
 *
 *  - `updateTicket` recibe UN id, no una lista: `toBody()` de tickets.js ya lo
 *    envuelve en `[id]`. Pasarle `[id]` mandaria `[[id]]`.
 *  - "Asignarme" no puede confiar en un id del navegador: se resuelve desde la
 *    sesion. Por eso la prueba manda un `persona` ajeno junto con `yo=1` y
 *    afirma que gana la sesion.
 *
 * Los modulos de servidor se sustituyen enteros (como en ../page-server.test.js):
 * `vitest.config.js` no resuelve `$env/dynamic/private`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const entorno = vi.hoisted(() => ({ env: /** @type {Record<string, string>} */ ({}) }));
vi.mock('$env/dynamic/private', () => entorno);
const sesion = vi.hoisted(() => ({ tenant: /** @type {string | null} */ (null) }));

const updateTicket = vi.fn();
const tomarTicket = vi.fn();
const getTicket = vi.fn();
const replyToTicket = vi.fn();
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicket: (...args) => getTicket(...args),
  replyToTicket: (...args) => replyToTicket(...args),
  updateTicket: (...args) => updateTicket(...args),
  tomarTicket: (...args) => tomarTicket(...args)
}));

const PERSONAS = [
  { id: 'p-admin', name: 'Ana Admin', email: 'admin@x.test' },
  { id: 'p-tec', name: 'Luis Técnico', email: 'tec@x.test' }
];
vi.mock('$lib/server/v2/org-people.js', () => ({
  getOrgPeopleAndTeams: async () => ({ people: PERSONAS, teams: [] }),
  // La regla real, copiada: por correo, sin distinguir mayusculas.
  resolveMe: (people, email) =>
    email ? (people.find((p) => p.email.toLowerCase() === email.toLowerCase())?.id ?? null) : null
}));
vi.mock('$lib/server/v2/form-errors.js', () => ({
  readableError: (_err, fallback) => fallback
}));
vi.mock('$lib/server/v2/resumen-agente.js', () => ({ leerResumenDelAgente: () => null }));
vi.mock('$lib/server/v2/areas.js', () => ({ leerAreas: async () => ({ areas: [], areaPorPersona: {} }) }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/autor.js', () => ({ autorDeSesion: () => ({}), claveIdempotencia: () => 'k' }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => sesion.tenant }));
//  El día de la EMPRESA, distinto a propósito del de hoy en UTC: si la acción
//  volviera a `toISOString()`, la prueba de cierre lo nota.
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2001-02-03' }));

const { actions, load } = await import('./+page.server.js');

describe('load: estadoConversacion', () => {
  beforeEach(() => {
    entorno.env = { PRIVATE_ASISTENTE_URL: 'http://motor.test' };
    sesion.tenant = 'empresa';
    getTicket.mockReset();
    getTicket.mockResolvedValue({ ticket: { id: 'caso-1', description: '' } });
  });

  /** @param {(url: string) => Promise<any>} respuesta */
  async function cargar(respuesta) {
    const fetch = vi.fn(respuesta);
    const datos = /** @type {any} */ (
      await load(/** @type {any} */ ({
        locals: { profile: { role: 'USER' }, user: { email: 'tec@x.test' } },
        cookies: { get: () => undefined },
        params: { id: 'caso-1' },
        fetch
      }))
    );
    return { datos, fetch };
  }
  const ok = (/** @type {any} */ cuerpo) => async () => ({ ok: true, json: async () => cuerpo });

  it('con conversacion detras: si', async () => {
    const { datos, fetch } = await cargar(ok({ conversacion: { id: 'c-1', canal: 'whatsapp' }, contexto: {} }));
    expect(await datos.estadoConversacion).toBe('si');
    // La misma busqueda que usa el envio: por el id del CASO.
    expect(fetch.mock.calls[0][0]).toContain('/conversaciones/por-caso/caso-1');
  });

  it('el motor contesto y no hay chat: no', async () => {
    const { datos } = await cargar(ok({ conversacion: null, contexto: {} }));
    expect(await datos.estadoConversacion).toBe('no');
  });

  it('el motor no contesto: no_se_pudo, NUNCA "no"', async () => {
    const caido = await cargar(async () => { throw new Error('ECONNREFUSED'); });
    expect(await caido.datos.estadoConversacion).toBe('no_se_pudo');
    const error = await cargar(async () => ({ ok: false, json: async () => ({}) }));
    expect(await error.datos.estadoConversacion).toBe('no_se_pudo');
  });

  it('sin motor configurado tampoco afirma que no hay chat', async () => {
    entorno.env = {};
    const { datos } = await cargar(ok({ conversacion: { id: 'c-1' } }));
    expect(await datos.estadoConversacion).toBe('no_se_pudo');
  });

  it('un colaborador no recibe el control de asignar; los nombres si, sin correos', async () => {
    const { datos } = await cargar(ok({ conversacion: null }));
    expect(datos.reparte).toBe(false);
    expect(datos.yo).toBe('p-tec');
    expect(datos.personas).toEqual([
      { id: 'p-admin', name: 'Ana Admin' },
      { id: 'p-tec', name: 'Luis Técnico' }
    ]);
  });
});

/**
 * @param {Record<string, string>} campos
 * @param {{ role?: string, email?: string }} [sesion]
 * @returns {any}
 */
function evento(campos, { role = 'ADMIN', email = 'admin@x.test' } = {}) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.set(k, v);
  return {
    cookies: { get: () => undefined },
    params: { id: 'caso-1' },
    request: { formData: async () => fd },
    locals: { profile: { role }, user: { email } }
  };
}

describe('?/asignar', () => {
  beforeEach(() => {
    updateTicket.mockReset();
    updateTicket.mockResolvedValue({});
  });

  it('un admin asigna a una persona: UN id, no una lista', async () => {
    const r = /** @type {any} */ (await actions.asignar(evento({ persona: 'p-tec' })));
    expect(updateTicket).toHaveBeenCalledTimes(1);
    const [, id, valores] = updateTicket.mock.calls[0];
    expect(id).toBe('caso-1');
    expect(valores).toEqual({ assigned_to: 'p-tec' });
    expect(Array.isArray(valores.assigned_to)).toBe(false);
    expect(r.asignadoNombre).toBe('Luis Técnico');
  });

  it('"Asignarme" sale de la sesion, no de lo que mande el navegador', async () => {
    await actions.asignar(evento({ yo: '1', persona: 'p-tec' }));
    expect(updateTicket.mock.calls[0][2]).toEqual({ assigned_to: 'p-admin' });
  });

  it('vacio deja el ticket sin responsable', async () => {
    await actions.asignar(evento({ persona: '' }));
    expect(updateTicket.mock.calls[0][2]).toEqual({ assigned_to: '' });
  });

  it('quien no es admin no escribe nada', async () => {
    const r = /** @type {any} */ (await actions.asignar(evento({ persona: 'p-tec' }, { role: 'USER' })));
    expect(r.status).toBe(403);
    expect(updateTicket).not.toHaveBeenCalled();
  });

  it('un id que no es de la organizacion no llega al API', async () => {
    const r = /** @type {any} */ (await actions.asignar(evento({ persona: 'p-ajeno' })));
    expect(r.status).toBe(400);
    expect(updateTicket).not.toHaveBeenCalled();
  });

  it('"Asignarme" sin perfil propio en la organizacion se niega', async () => {
    const r = /** @type {any} */ (await actions.asignar(evento({ yo: '1' }, { email: 'otro@x.test' })));
    expect(r.status).toBe(400);
    expect(updateTicket).not.toHaveBeenCalled();
  });

  it('si el API rechaza, lo dice', async () => {
    updateTicket.mockRejectedValue(new Error('400'));
    const r = /** @type {any} */ (await actions.asignar(evento({ persona: 'p-tec' })));
    expect(r.status).toBe(400);
    expect(r.data.error).toBe('No se pudo cambiar el responsable.');
  });
});

describe('?/tomar', () => {
  /** @param {number} status */
  const rechazo = (status) => Object.assign(new Error('x'), { status, body: {} });

  it('un colaborador toma por /tomar/: decide el backend, no el rol', async () => {
    tomarTicket.mockReset();
    tomarTicket.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.tomar(evento({}, { role: 'USER' })));
    expect(r).toEqual({ tomado: true });
    expect(tomarTicket.mock.lastCall[1]).toBe('caso-1');
  });

  it('409: otra persona lo tomo primero; 403: no es de su area', async () => {
    tomarTicket.mockReset();
    tomarTicket.mockRejectedValueOnce(rechazo(409)).mockRejectedValueOnce(rechazo(403));
    const a = /** @type {any} */ (await actions.tomar(evento({}, { role: 'USER' })));
    expect(a.status).toBe(409);
    expect(a.data.error).toMatch(/primero/);
    const b = /** @type {any} */ (await actions.tomar(evento({}, { role: 'USER' })));
    expect(b.status).toBe(403);
    expect(b.data.error).toMatch(/área/);
  });
});

/*
 * ?/reply Y LA PRIMERA RESPUESTA (28/10/2026). Con chat detrás, la marca el
 * motor y sólo si WhatsApp aceptó el mensaje; el comentario del CRM la marcaba
 * igual aunque al cliente no le hubiera llegado nada. Sin chat, el comentario
 * ES la respuesta y la sigue marcando.
 */
describe('?/reply: quién marca la primera respuesta', () => {
  beforeEach(() => {
    entorno.env = { PRIVATE_ASISTENTE_URL: 'http://motor.test' };
    sesion.tenant = 'empresa';
    replyToTicket.mockReset();
    replyToTicket.mockResolvedValue({});
  });

  /** @param {(url: string) => Promise<any>} motor */
  async function responder(motor) {
    const e = /** @type {any} */ (evento({ body: 'Ya revisamos su equipo' }));
    e.fetch = vi.fn(motor);
    const r = /** @type {any} */ (await actions.reply(e));
    return { r, datos: replyToTicket.mock.calls[0]?.[2] };
  }
  const motorDice = (/** @type {number} */ status, /** @type {any} */ cuerpo) => async () => ({
    ok: status < 300,
    status,
    json: async () => cuerpo
  });

  it('salió por WhatsApp y Meta la aceptó: el comentario NO la marca (la marcó el motor)', async () => {
    const { datos } = await responder(
      motorDice(201, { ok: true, resultado: 'aceptado', aceptado_por_meta: true })
    );
    expect(datos.sinPrimeraRespuesta).toBe(true);
  });

  it('el motor la rechazó: tampoco, y el aviso dice que no llegó', async () => {
    const { r, datos } = await responder(motorDice(409, { error: 'La IA atiende este chat.' }));
    expect(datos.sinPrimeraRespuesta).toBe(true);
    expect(r.aviso).toMatch(/No le llegó al cliente/);
  });

  it('el motor no contestó: tampoco (si el mensaje salió, lo marcó el motor)', async () => {
    const { datos } = await responder(async () => {
      throw new Error('ECONNREFUSED');
    });
    expect(datos.sinPrimeraRespuesta).toBe(true);
  });

  it('un ticket sin chat: el comentario ES la respuesta y la marca', async () => {
    const { datos } = await responder(motorDice(404, { sin_conversacion: true }));
    expect(datos.sinPrimeraRespuesta).toBe(false);
  });

  it('sin motor configurado: la marca el comentario, como siempre', async () => {
    entorno.env = {};
    const { datos } = await responder(async () => {
      throw new Error('no deberia llamarse');
    });
    expect(datos.sinPrimeraRespuesta).toBe(false);
  });
});

describe('?/setStatus', () => {
  beforeEach(() => {
    updateTicket.mockReset();
    updateTicket.mockResolvedValue({});
  });

  it('cerrar pone la fecha de la EMPRESA, no la del servidor en UTC', async () => {
    await actions.setStatus(evento({ status: 'Closed' }));
    const [, , valores] = updateTicket.mock.calls[0];
    expect(valores).toEqual({ status: 'Closed', closed_on: '2001-02-03' });
  });

  it('otro estado no lleva fecha de cierre', async () => {
    await actions.setStatus(evento({ status: 'Pending' }));
    const [, , valores] = updateTicket.mock.calls[0];
    expect(valores).toEqual({ status: 'Pending' });
  });
});
