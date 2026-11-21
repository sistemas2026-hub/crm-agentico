import { describe, it, expect, vi, beforeEach } from 'vitest';

const listarPropuestas = vi.fn();
const leerAutonomia = vi.fn();
const leerFallas = vi.fn();
const leerDiaPublicado = vi.fn();
const leerMaterialDelDia = vi.fn();

vi.mock('$lib/server/v2/supervisor-noc.js', () => ({ listarPropuestas, leerAutonomia }));
vi.mock('$lib/server/v2/fallas-de-red.js', () => ({ leerFallas }));
vi.mock('$lib/server/v2/dia-publicado.js', () => ({ leerDiaPublicado }));
vi.mock('$lib/server/v2/material-del-dia.js', () => ({ leerMaterialDelDia }));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2026-11-21' }));

const { GET } = await import('./+server.js');
const { leerPulso, _olvidarLosPulsos } = await import('$lib/server/v2/pulso-noc.js');

/** @param {string} role */
const evento = (role, org = 'org-1') => /** @type {any} */ ({
  locals: { user: { id: 1 }, profile: { role }, org: { id: org } },
  cookies: {},
  fetch: vi.fn()
});

beforeEach(() => {
  _olvidarLosPulsos();
  listarPropuestas.mockReset().mockResolvedValue({ resultados: [{ sla_estado: 'VENCIDA' }], error: null });
  leerAutonomia.mockReset().mockResolvedValue({ permitido: true });
  leerFallas.mockReset().mockResolvedValue({ fallas: [] });
  leerDiaPublicado.mockReset().mockResolvedValue({ publicado: { cuadrillas: [{}], cuentas: { esperan: 3 } }, error: false });
  leerMaterialDelDia.mockReset().mockResolvedValue({ material: { cuentas: { con_faltantes: 1 } }, error: false });
});

describe('GET /supervisor-noc/pulso', () => {
  it('solo los roles de gestión', async () => {
    const r = await GET(evento('AGENT'));
    expect(r.status).toBe(403);
    expect(listarPropuestas).not.toHaveBeenCalled();
  });

  it('sin sesión, 401', async () => {
    const r = await GET(/** @type {any} */ ({ locals: {}, cookies: {}, fetch: vi.fn() }));
    expect(r.status).toBe(401);
  });

  it('devuelve las seis fichas y no se guarda en caché del navegador', async () => {
    const r = await GET(evento('ADMIN'));
    expect(r.headers.get('cache-control')).toBe('no-store');
    const d = await r.json();
    expect(d.fichas.map((/** @type {any} */ f) => f.valor)).toEqual(['1', '0', '0/1', '3', '1', 'Actúa']);
  });
});

describe('leerPulso', () => {
  it('una fuente que falla no tumba las demás: esa dice «sin dato»', async () => {
    leerFallas.mockRejectedValue(new Error('backend caído'));
    listarPropuestas.mockResolvedValue({ resultados: [], error: 'no se pudo' });
    const { fichas } = await leerPulso(evento('ADMIN'));
    expect(fichas[0].valor).toBeNull();
    expect(fichas[1].valor).toBeNull();
    expect(fichas[3].valor).toBe('3');
  });

  it('se recuerda un minuto por empresa', async () => {
    await leerPulso(evento('ADMIN'), 1000);
    await leerPulso(evento('ADMIN'), 30_000);
    expect(listarPropuestas).toHaveBeenCalledTimes(1);
    await leerPulso(evento('ADMIN'), 62_000);
    expect(listarPropuestas).toHaveBeenCalledTimes(2);
    await leerPulso(evento('ADMIN', 'org-2'), 62_500);
    expect(listarPropuestas).toHaveBeenCalledTimes(3);
  });
});
