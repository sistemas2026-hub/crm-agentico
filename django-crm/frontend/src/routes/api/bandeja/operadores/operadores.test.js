import { describe, it, expect, vi } from 'vitest';

/**
 * La lista del equipo para el panel de carga (29/10/2026). Solo ADMIN, porque
 * es a quién se le puede reasignar: mostrar el panel en la pantalla no es lo
 * que autoriza, lo es esta ruta.
 */
const operadoresDeLaOrg = vi.fn(async (/** @type {any[]} */ ..._a) => [{ usuario_id: 'u-1', nombre: 'Ana' }]);
vi.mock('$lib/server/v2/operadores.js', () => ({
  operadoresDeLaOrg: (...a) => operadoresDeLaOrg(...a),
  rolDeSesion: (locals) => String(locals?.profile?.role ?? 'USER').toUpperCase()
}));

const { GET } = await import('./+server.js');
const ev = (rol) => /** @type {any} */ ({ locals: { user: { id: 'u' }, profile: { role: rol } }, cookies: {} });

describe('GET /api/bandeja/operadores', () => {
  it('un administrador recibe el equipo', async () => {
    const r = await GET(ev('ADMIN'));
    expect(r.status).toBe(200);
    expect((await r.json()).operadores).toEqual([{ usuario_id: 'u-1', nombre: 'Ana' }]);
  });
  it('otro rol no', async () => {
    operadoresDeLaOrg.mockClear();
    const r = await GET(ev('USER'));
    expect(r.status).toBe(403);
    expect(operadoresDeLaOrg).not.toHaveBeenCalled();
  });
});
