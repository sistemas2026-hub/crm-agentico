import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Equipo: la puerta de rol está en el servidor, no en que Django falle
 * (12/11/2026, auditoría del menú §4.2).
 *
 * Antes, para un miembro la carga dependía de que `listTeam` devolviera
 * `forbidden`, y aun así le pedía al motor las asignaciones (áreas por persona,
 * identidades en el sistema externo). Lo que se afirma es el EFECTO: un no
 * administrador no dispara NINGUNA lectura ni escritura.
 */
const llamadas = vi.hoisted(() => ({ listTeam: 0, escrituras: 0 }));
vi.mock('$lib/server/v2/team.js', () => ({
  ROLES: ['ADMIN', 'USER', 'BODEGA'],
  listTeam: async () => {
    llamadas.listTeam++;
    return { active: [], inactive: [], teams: [], totals: { count: 0, admins: 0 } };
  },
  inviteUser: async () => { llamadas.escrituras++; },
  setRole: async () => { llamadas.escrituras++; },
  setStatus: async () => { llamadas.escrituras++; },
  setPassword: async () => { llamadas.escrituras++; },
  updateUser: async () => { llamadas.escrituras++; },
  perfilPorCorreo: async () => null,
  casosDe: async () => [],
  reasignarCaso: async () => { llamadas.escrituras++; }
}));
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: (_e, m) => m }));
vi.mock('$lib/server/v2/tenant.js', () => ({
  tenantDeLaSesion: async () => 'empresa',
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'empresa' })
}));

const { load, actions } = await import('./+page.server.js');

const fetchFalso = vi.fn(async () => ({ ok: true, json: async () => ({ agentes: [], areas: [] }) }));

/** @param {string} rol @param {Record<string, string>} [campos] */
function evento(rol, campos = {}) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.append(k, v);
  return /** @type {any} */ ({ locals: { profile: { role: rol } }, cookies: { get: () => 'jwt' },
    fetch: fetchFalso, request: { formData: async () => fd } });
}

beforeEach(() => {
  llamadas.listTeam = 0;
  llamadas.escrituras = 0;
  fetchFalso.mockClear();
});

describe('equipo: solo administradores', () => {
  for (const rol of ['USER', 'BODEGA', undefined]) {
    it(`la carga de un ${rol ?? 'sin perfil'} no lee nada, ni del CRM ni del motor`, async () => {
      const d = /** @type {any} */ (await load(evento(/** @type {any} */ (rol))));
      expect(d).toEqual({ forbidden: true });
      expect(llamadas.listTeam).toBe(0);
      expect(fetchFalso).not.toHaveBeenCalled();
    });
  }

  it('un administrador sí carga el equipo y las áreas', async () => {
    const d = /** @type {any} */ (await load(evento('ADMIN')));
    expect(d.forbidden).toBeUndefined();
    expect(llamadas.listTeam).toBe(1);
    expect(fetchFalso).toHaveBeenCalled();
  });

  it('ninguna acción escribe para quien no es administrador', async () => {
    const campos = { userId: 'u1', profileId: 'p1', role: 'ADMIN', status: 'Active', email: 'a@b.co', name: 'A' };
    for (const accion of ['actualizar', 'invite', 'setRole', 'setStatus']) {
      const r = /** @type {any} */ (await /** @type {any} */ (actions)[accion](evento('USER', campos)));
      expect(r.status, accion).toBe(403);
    }
    expect(llamadas.escrituras).toBe(0);
    expect(llamadas.listTeam).toBe(0);
    expect(fetchFalso).not.toHaveBeenCalled();
  });
});
