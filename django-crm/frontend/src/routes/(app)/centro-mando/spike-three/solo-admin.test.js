import { describe, it, expect, vi } from 'vitest';

/**
 * El prototipo de Three.js es de ADMIN, en el servidor (12/11/2026): trae
 * datos reales de la empresa y no hay decisión tomada sobre él. Un miembro que
 * escribe la URL vuelve al centro de mando y no se lee nada del motor.
 */
const leidas = vi.hoisted(() => ({ n: 0 }));
vi.mock('../+page.server.js', () => ({
  load: async () => {
    leidas.n += 1;
    return { agentes: [], areas: [], organizacion: null, acciones: null, error: null, rol: 'ADMIN' };
  }
}));

const { load } = await import('./+page.server.js');

describe('/centro-mando/spike-three', () => {
  it('un USER vuelve al centro de mando sin leer nada', async () => {
    await expect(load(/** @type {any} */ ({ locals: { profile: { role: 'USER' } } }))).rejects.toMatchObject({
      status: 303,
      location: '/centro-mando'
    });
    expect(leidas.n).toBe(0);
  });

  it('un ADMIN lo abre con la misma carga que el centro de mando', async () => {
    const d = await load(/** @type {any} */ ({ locals: { profile: { role: 'ADMIN' } } }));
    expect(d).toMatchObject({ agentes: [], error: null });
    expect(leidas.n).toBe(1);
  });
});
