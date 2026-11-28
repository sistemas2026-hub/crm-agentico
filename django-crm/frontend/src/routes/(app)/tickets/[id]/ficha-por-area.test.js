/**
 * EL DETALLE DEL TICKET NO LE ENTREGA LA CÉDULA A QUIEN NO LA PUEDE VER  (12/11/2026)
 *
 * La cadena: el load pide al motor el contexto del caso (/conversaciones/
 * por-caso, que trae la ficha ENTERA porque el despacho del backend la
 * necesita) y, en paralelo, qué puede ver quien mira (/ficha-cliente/
 * visibilidad). Lo que se afirma es lo que RECIBE la página (`data.contexto`),
 * no que exista el filtro:
 *
 *  - un rol sin permiso no recibe la cédula, y la ficha dice que está oculta;
 *  - quien mira se identifica con el rol de la SESIÓN y su Profile.id, nunca
 *    con algo del navegador;
 *  - si el motor no da la visibilidad, no pasa ningún dato personal.
 *
 * Los módulos de servidor se sustituyen como en detalle-servidor.test.js; el
 * filtro (lib/server/v2/ficha-visible.js) es el REAL.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const entorno = vi.hoisted(() => ({ env: /** @type {Record<string, string>} */ ({}) }));
vi.mock('$env/dynamic/private', () => entorno);
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicket: async () => ({ ticket: { id: 'caso-1', description: '', external_service_id: '5832' } }),
  replyToTicket: vi.fn(), updateTicket: vi.fn(), tomarTicket: vi.fn()
}));
vi.mock('$lib/server/v2/org-people.js', () => ({
  getOrgPeopleAndTeams: async () => ({
    people: [{ id: 'p-tec', name: 'Luis', email: 'tec@x.test' }, { id: 'p-admin', name: 'Ana', email: 'admin@x.test' }],
    teams: []
  }),
  resolveMe: (people, email) => people.find((p) => p.email === email)?.id ?? null
}));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: (_e, f) => f }));
vi.mock('$lib/server/v2/resumen-agente.js', () => ({ leerResumenDelAgente: () => null }));
vi.mock('$lib/server/v2/areas.js', () => ({ leerAreas: async () => ({ areas: [], areaPorPersona: {} }) }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({ 'X-Servicio-Token': 't' }) }));
vi.mock('$lib/server/v2/autor.js', () => ({ autorDeSesion: () => ({}), claveIdempotencia: () => 'k' }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2001-02-03' }));

const { load } = await import('./+page.server.js');

const CONTEXTO = {
  wisphub_perfil: 'https://isp.test/cliente/5832',
  cliente: { nombre: 'TITULAR', cedula: '1234567890', telefono: '3001112233',
             direccion: 'CALLE 1', estado: 'Activo', plan: 'PLAN 100', plan_id: 7,
             coordenadas: '4.1,-74.1', ip: '10.0.0.9' },
  identidad: { servicio: '5832', origen: 'caso' }
};
const SIN_CEDULA = {
  campos: ['direccion', 'estado', 'nombre', 'plan', 'plan_id', 'plan_internet', 'telefono'],
  ocultos: ['cedula', 'email', 'coordenadas'], criterio: 'defecto'
};
const TODO = {
  campos: ['cedula', 'coordenadas', 'direccion', 'email', 'estado', 'nombre', 'plan', 'plan_id', 'plan_internet', 'telefono'],
  ocultos: [], criterio: 'gestion'
};

/** @param {any} visibilidad  null = el motor no la da */
function motor(visibilidad) {
  return vi.fn(async (/** @type {string} */ url) => {
    if (url.includes('/ficha-cliente/visibilidad')) {
      return visibilidad ? { ok: true, json: async () => visibilidad } : { ok: false, json: async () => ({}) };
    }
    return { ok: true, json: async () => ({ conversacion: null, contexto: structuredClone(CONTEXTO) }) };
  });
}

async function cargar(/** @type {any} */ fetch, role = 'USER', email = 'tec@x.test') {
  const datos = /** @type {any} */ (await load(/** @type {any} */ ({
    locals: { profile: { role }, user: { email } },
    cookies: { get: () => undefined },
    params: { id: 'caso-1' },
    fetch
  })));
  return { contexto: await datos.contexto, fetch };
}

describe('la ficha del titular en el detalle del ticket', () => {
  beforeEach(() => {
    entorno.env = { PRIVATE_ASISTENTE_URL: 'http://motor.test' };
  });

  it('un rol sin permiso NO recibe la cédula, y la ficha dice que está oculta', async () => {
    const { contexto } = await cargar(motor(SIN_CEDULA));
    expect(contexto.cliente.cedula).toBeUndefined();
    expect(JSON.stringify(contexto)).not.toContain('1234567890');
    expect(contexto.cliente._ocultos).toContain('cedula');
    // Lo que sí puede ver llega, con el plan por su alias.
    expect(contexto.cliente.telefono).toBe('3001112233');
    expect(contexto.cliente.plan).toBe('PLAN 100');
    // Lo no clasificado tampoco pasa; lo que no es la ficha, sí.
    expect(contexto.cliente.ip).toBeUndefined();
    expect(contexto.wisphub_perfil).toBe(CONTEXTO.wisphub_perfil);
  });

  it('le pregunta al motor con el rol de la SESIÓN y el Profile.id de quien mira', async () => {
    const { fetch } = await cargar(motor(SIN_CEDULA));
    const url = fetch.mock.calls.map((c) => String(c[0])).find((u) => u.includes('/ficha-cliente/visibilidad'));
    const qs = new URL(/** @type {string} */ (url)).searchParams;
    expect(qs.get('rol')).toBe('USER');
    expect(qs.get('perfil')).toBe('p-tec');
    expect(qs.get('tenant')).toBe('empresa');
  });

  it('gestión recibe la ficha entera', async () => {
    const { contexto } = await cargar(motor(TODO), 'ADMIN', 'admin@x.test');
    expect(contexto.cliente.cedula).toBe('1234567890');
    expect(contexto.cliente._ocultos).toEqual([]);
  });

  it('si el motor no da la visibilidad, no pasa ningún dato del titular', async () => {
    const { contexto } = await cargar(motor(null));
    expect(contexto.cliente).toEqual({ _ocultos: [], _sinCriterio: true });
  });
});
