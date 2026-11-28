import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * EL BUZÓN DE LAS SOLICITUDES LO EDITA LA EMPRESA (31/10/2026)
 * ===========================================================
 * Es un dato de cada empresa, no del servidor (CLAUDE.md §3.3): el
 * administrador lo carga en Ajustes → Organización. Se afirma sobre lo que
 * LLEGA al backend: que el campo viaja, recortado, junto con lo demás. Los
 * nombres del módulo real se conservan (importActual); solo se sustituye la
 * llamada al backend.
 */

const updateOrgSettings = vi.fn();

//  El módulo real importa api-helpers, que pide '$env' de SvelteKit: se
//  sustituye solo eso, para que EDITABLE_FIELDS sea la lista VERDADERA.
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: async () => ({}) }));

vi.mock('$lib/server/v2/organization.js', async (importOriginal) => {
  const real = /** @type {any} */ (await importOriginal());
  return {
    ...real,
    getOrgSettings: async () => ({ org: {}, can_edit: true }),
    updateOrgSettings: (/** @type {any[]} */ ...a) => updateOrgSettings(...a),
    listTimezones: async () => []
  };
});
vi.mock('@sveltejs/kit', async (importOriginal) => {
  const real = /** @type {any} */ (await importOriginal());
  return { ...real, redirect: (/** @type {number} */ s, /** @type {string} */ l) => ({ redireccion: l, s }) };
});

const { actions } = await import('./+page.server.js');

/** @param {Record<string, string>} campos */
function evento(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({
    request: new Request('http://x/settings/organization/edit?/save', { method: 'POST', body: f }),
    cookies: {}
  });
}

beforeEach(() => {
  updateOrgSettings.mockReset();
  updateOrgSettings.mockResolvedValue({});
});

describe('el correo de las solicitudes', () => {
  it('viaja al backend, recortado', async () => {
    await actions.save(evento({ name: 'Mi ISP', correo_solicitudes: '  ventas@miisp.co, jefe@miisp.co  ' }));
    expect(updateOrgSettings).toHaveBeenCalledWith(expect.anything(),
      expect.objectContaining({ correo_solicitudes: 'ventas@miisp.co, jefe@miisp.co' }));
  });

  it('si no viene en el formulario no se toca (el PATCH es parcial)', async () => {
    await actions.save(evento({ name: 'Mi ISP' }));
    expect(updateOrgSettings.mock.calls[0][1]).not.toHaveProperty('correo_solicitudes');
  });
});
