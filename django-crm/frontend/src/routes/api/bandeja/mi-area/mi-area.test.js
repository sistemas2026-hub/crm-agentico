import { describe, it, expect, vi } from 'vitest';

/**
 * «Mi área» (T22). Nace de un defecto que `svelte-check` cazó antes del
 * deploy: la primera versión leía `locals.profile.id`, que la sesión NO
 * trae, y el filtro no habría aparecido nunca. Ahora se resuelve como en
 * Tickets: la persona por su email, su área en las del motor.
 */
vi.mock('$lib/server/v2/org-people.js', () => ({
  getOrgPeopleAndTeams: async () => ({ people: [{ id: 'p-ana', email: 'ana@x.co' }] }),
  resolveMe: (people, email) => people.find((p) => p.email === email)?.id ?? null
}));
vi.mock('$lib/server/v2/areas.js', () => ({
  leerAreas: async () => ({ areas: [], areaPorPersona: { 'p-ana': 'soporte_tecnico' } })
}));

const { GET } = await import('./+server.js');
const ev = (email) => /** @type {any} */ ({ locals: { user: { email } }, cookies: {}, fetch: vi.fn() });

describe('GET /api/bandeja/mi-area', () => {
  it('devuelve el área de quien mira', async () => {
    expect((await (await GET(ev('ana@x.co'))).json()).area).toBe('soporte_tecnico');
  });
  it('sin área conocida, null: no se inventa una', async () => {
    expect((await (await GET(ev('otro@x.co'))).json()).area).toBeNull();
  });
});
