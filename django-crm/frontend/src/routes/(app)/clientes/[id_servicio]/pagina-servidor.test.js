import { describe, it, expect, vi, beforeEach } from 'vitest';

/*
 * La ficha del cliente (12/11/2026): del CRM y del motor a lo que recibe la
 * página, y las tres respuestas que no se confunden: «no hay», «no se pudo» y
 * «no es para tu rol».
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa_a' }));

const { load } = await import('./+page.server.js');

const CRM = {
  servicio: '4986',
  tickets: [{ id: 't1', nombre: 'Sin internet', estado: 'New' }],
  ordenes: [{ id: 'o1', numero: 188, puede_abrir: true, cuadrilla: 'Norte' }],
  solicitudes: null
};
const MOTOR = {
  servicio: '4986',
  conversaciones: [{ id: 'c1', canal: 'whatsapp', canal_operativo: true }],
  contexto: { cliente: { nombre: 'Ana', plan: 'ELITE' }, equipo: { onu_status: 'Online' } }
};

/** @param {any} fetch @param {string} [servicio] */
const evento = (fetch, servicio = '4986') => /** @type {any} */ ({
  params: { id_servicio: servicio },
  cookies: {},
  locals: { user: { id: 1 }, profile: { role: 'USER' } },
  fetch
});

beforeEach(() => {
  apiRequest.mockReset();
});

describe('la ficha del cliente', () => {
  it('junta las dos mitades tal como llegan', async () => {
    apiRequest.mockResolvedValue(CRM);
    const fetch = vi.fn(async () => ({ ok: true, json: async () => MOTOR }));
    const d = /** @type {any} */ (await load(evento(fetch)));
    expect(d.tickets).toEqual(CRM.tickets);
    expect(d.ordenes).toEqual(CRM.ordenes);
    // null del backend = «no es para tu rol»: no se vuelve una lista vacía.
    expect(d.solicitudes).toBeNull();
    expect(d.conversaciones).toEqual(MOTOR.conversaciones);
    expect(d.contexto).toEqual(MOTOR.contexto);
    expect(d.motorSinRespuesta).toBe(false);
  });

  it('el motor caído se dice como tal, y lo del CRM sale igual', async () => {
    apiRequest.mockResolvedValue(CRM);
    const fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    const d = /** @type {any} */ (await load(evento(fetch)));
    expect(d.motorSinRespuesta).toBe(true);
    expect(d.tickets).toEqual(CRM.tickets);
  });

  it('un servicio inválido es 404 y no sale a ningún lado', async () => {
    const fetch = vi.fn();
    await expect(load(evento(fetch, 'a b'))).rejects.toMatchObject({ status: 404 });
    expect(apiRequest).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
});
