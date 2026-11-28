import { describe, it, expect, vi } from 'vitest';

/**
 * Tomar una conversación y quedarse el ticket del CRM (12/11/2026).
 * Lo que se mide: el ticket se asigna SOLO a quien coincide por correo,
 * exactamente una vez; cuando no se puede, la respuesta lo dice
 * (`aviso_ticket`) en vez de devolver `asignado: null` callada.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
const tickets = vi.hoisted(() => ({ owners: /** @type {any[]} */ ([]), fallar: false, asignaciones: /** @type {any[]} */ ([]) }));
vi.mock('$lib/server/v2/tickets.js', () => ({
  getTicketFormOptions: async () => ({ owners: tickets.owners }),
  updateTicket: async (/** @type {any} */ _e, /** @type {string} */ id, /** @type {any} */ datos) => {
    if (tickets.fallar) throw Object.assign(new Error('400 crudo del CRM con datos'), { status: 400 });
    tickets.asignaciones.push({ id, ...datos });
  }
}));

const { POST } = await import('./+server.js');
const { perfilPropio } = await import('./propio.js');

/** @param {any} cuerpo @param {any} [user] @param {any} [motor] */
async function tomar(cuerpo, user = { id: 'u1', name: 'Ana', email: 'Ana@Empresa.co' }, motor = { aplicada: true }) {
  tickets.asignaciones = [];
  const fetch = vi.fn(async () => new Response(JSON.stringify(motor), { status: 200 }));
  const r = await POST(/** @type {any} */ ({
    request: { json: async () => cuerpo }, params: { id: 'c1' }, locals: { user }, fetch, cookies: {}
  }));
  return { r, datos: await r.json(), fetch };
}

describe('perfilPropio', () => {
  const owners = [{ id: 'p1', name: 'ana@empresa.co' }, { id: 'p2', name: '' }, { id: 'p3', name: 'luis@empresa.co' }];
  it('empareja correo contra correo, sin mayúsculas ni espacios', () => {
    expect(perfilPropio(owners, ' ANA@empresa.co ').propio?.id).toBe('p1');
  });
  it('un correo vacío no empareja con el perfil sin correo', () => {
    expect(perfilPropio(owners, '')).toEqual({ propio: null, motivo: 'sin_correo' });
    expect(perfilPropio(owners, undefined).propio).toBeNull();
  });
  it('dos perfiles con el mismo correo: ninguno', () => {
    expect(perfilPropio([...owners, { id: 'p9', name: 'ana@empresa.co' }], 'ana@empresa.co'))
      .toEqual({ propio: null, motivo: 'ambiguo' });
  });
  it('nadie coincide', () => {
    expect(perfilPropio(owners, 'otro@x.co').motivo).toBe('sin_perfil');
  });
});

describe('POST /api/conversaciones/[id]/atender', () => {
  it('al tomar, el ticket queda a nombre de quien coincide por correo, sin aviso', async () => {
    tickets.owners = [{ id: 'p1', name: 'ana@empresa.co' }]; tickets.fallar = false;
    const { datos } = await tomar({ caso_id: 'k1' });
    expect(tickets.asignaciones).toEqual([{ id: 'k1', assigned_to: 'p1' }]);
    expect(datos.asignado?.id).toBe('p1');
    expect(datos.aviso_ticket).toBeUndefined();
  });

  it('si el usuario no está entre los responsables, lo dice', async () => {
    tickets.owners = [{ id: 'p3', name: 'luis@empresa.co' }]; tickets.fallar = false;
    const { r, datos } = await tomar({ caso_id: 'k1' });
    expect(r.status).toBe(200);
    expect(tickets.asignaciones).toEqual([]);
    expect(datos.asignado).toBeNull();
    expect(datos.aviso_ticket).toMatch(/quedó sin asignarte/);
  });

  it('si el CRM rechaza la asignación, lo dice sin el error crudo', async () => {
    tickets.owners = [{ id: 'p1', name: 'ana@empresa.co' }]; tickets.fallar = true;
    const { datos } = await tomar({ caso_id: 'k1' });
    expect(datos.aviso_ticket).toMatch(/no aceptó/);
    expect(JSON.stringify(datos)).not.toMatch(/crudo/);
  });

  it('al soltar, o si el motor no cambió nada, no se toca el ticket ni se avisa', async () => {
    tickets.owners = []; tickets.fallar = false;
    for (const [cuerpo, motor] of [[{ caso_id: 'k1', soltar: true }, { aplicada: true }],
                                    [{ caso_id: 'k1' }, { aplicada: false }]]) {
      const { datos } = await tomar(cuerpo, undefined, motor);
      expect(tickets.asignaciones).toEqual([]);
      expect(datos.aviso_ticket).toBeUndefined();
    }
  });
});
