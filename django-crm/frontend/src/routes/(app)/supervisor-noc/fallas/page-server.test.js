import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * FALLAS DE RED: LO QUE LLEGA AL BACKEND (30/10/2026)
 * ===================================================
 * Se afirma sobre el EFECTO: a qué situación se le pide preparar o aprobar, y
 * qué frase lee la persona cuando no se puede. Sin rol o con un id que no es
 * un UUID no viaja nada. Los módulos de servidor se sustituyen con `vi.mock`.
 */

const leerFallas = vi.fn();
const prepararAviso = vi.fn();
const aprobarAviso = vi.fn();

vi.mock('$lib/server/v2/fallas-de-red.js', () => ({
  leerFallas: (/** @type {any[]} */ ...a) => leerFallas(...a),
  prepararAviso: (/** @type {any[]} */ ...a) => prepararAviso(...a),
  aprobarAviso: (/** @type {any[]} */ ...a) => aprobarAviso(...a)
}));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({
  zonaDeLaEmpresa: async () => 'America/Lima'
}));

const { actions, load } = await import('./+page.server.js');

const JEFA = { profile: { role: 'OPERACIONES' } };
const ID = '0b7c6f4e-1d2a-4b3c-9d8e-112233445566';

/** @param {Record<string, string>} campos @param {any} [locals] */
function evento(campos, locals = JEFA) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({
    request: new Request('http://x/supervisor-noc/fallas', { method: 'POST', body: f }),
    cookies: {},
    locals
  });
}

beforeEach(() => {
  for (const f of [leerFallas, prepararAviso, aprobarAviso]) f.mockReset();
});

describe('la lista', () => {
  it('la gestión ve las fallas, en la zona de la empresa', async () => {
    leerFallas.mockResolvedValue({ fallas: [{ id: ID }] });
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ cookies: {}, locals: JEFA })));
    expect(d).toMatchObject({ puedeVer: true, fallas: [{ id: ID }], zona: 'America/Lima' });
  });

  it('sin rol de gestión ni se le pregunta al backend', async () => {
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ cookies: {}, locals: { profile: { role: 'USER' } } })));
    expect(d.puedeVer).toBe(false);
    expect(leerFallas).not.toHaveBeenCalled();
  });
});

describe('preparar y aprobar', () => {
  it('preparar pide la vista previa de ESA caída y la devuelve', async () => {
    prepararAviso.mockResolvedValue({ clientes: 12, sin_cliente: 1 });
    const r = await actions.preparar(evento({ situacion: ID }));
    expect(prepararAviso).toHaveBeenCalledWith(expect.anything(), ID);
    expect(r).toEqual({ situacion: ID, preparada: { clientes: 12, sin_cliente: 1 } });
  });

  it('aprobar manda la aprobación de ESA caída', async () => {
    aprobarAviso.mockResolvedValue({ aviso: { clientes: 12, estado: 'en_curso' } });
    const r = await actions.aprobar(evento({ situacion: ID }));
    expect(aprobarAviso).toHaveBeenCalledWith(expect.anything(), ID);
    expect(r).toEqual({ situacion: ID, aprobada: { clientes: 12, estado: 'en_curso' } });
  });

  it('un rechazo del backend se lee como frase, no como código', async () => {
    aprobarAviso.mockRejectedValue({ body: { error: 'AVISO_APAGADO' } });
    const r = /** @type {any} */ (await actions.aprobar(evento({ situacion: ID })));
    expect(r.status).toBe(400);
    expect(r.data.error).toMatch(/apagado en Mensajes automáticos/);
  });

  it('un 202 «cargando» es un aviso para volver, no un éxito', async () => {
    aprobarAviso.mockResolvedValue({ error: 'CARGANDO' });
    const r = /** @type {any} */ (await actions.aprobar(evento({ situacion: ID })));
    expect(r.status).toBe(400);
    expect(r.data.error).toMatch(/armando la lista/);
  });

  it('sin rol o con un id raro no viaja nada', async () => {
    const r1 = /** @type {any} */ (await actions.aprobar(evento({ situacion: ID }, { profile: { role: 'USER' } })));
    const r2 = /** @type {any} */ (await actions.aprobar(evento({ situacion: '../1' })));
    expect(r1.status).toBe(403);
    expect(r2.status).toBe(400);
    expect(aprobarAviso).not.toHaveBeenCalled();
  });
});
