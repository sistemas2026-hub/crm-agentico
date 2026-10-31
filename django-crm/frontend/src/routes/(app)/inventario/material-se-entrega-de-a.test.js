import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { actions } = await import('./+page.server.js');

/**
 * «Se entrega de a» (29/10/2026): de a cuánto reparte el Supervisor un material
 * cuando la bodega no alcanza --el drop, de a 50 m--. La regla y sus rechazos
 * están probados en `test_catalogo_materiales.py`; acá se mide que el formulario
 * lo mande, y que vacío no pise el que ya tenía.
 */
function evento(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({
    request: { formData: async () => f },
    cookies: { get: () => 'token' }
  });
}

const MATERIAL = { codigo: 'DROP', nombre: 'Cable drop', clase: 'bobina', unidad: 'm' };

describe('«Se entrega de a» en el formulario de un material', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ codigo: 'DROP' });
  });

  it('al dar de alta lo manda, sin espacios', async () => {
    await actions.material(evento({ ...MATERIAL, se_entrega_de_a: ' 50 ' }));
    const [, opciones] = apiRequest.mock.calls[0];
    expect(opciones.body.se_entrega_de_a).toBe('50');
  });

  it('al editar lo manda con lo demás', async () => {
    await actions.material(evento({ ...MATERIAL, material_id: 'm-1', se_entrega_de_a: '100,5' }));
    const [endpoint, opciones] = apiRequest.mock.calls[0];
    expect(endpoint).toContain('m-1');
    expect(opciones.body.se_entrega_de_a).toBe('100,5');
  });

  it('vacío no se manda: el servidor deja el que tenía', async () => {
    await actions.material(evento({ ...MATERIAL, material_id: 'm-1', se_entrega_de_a: '  ' }));
    const [, opciones] = apiRequest.mock.calls[0];
    expect(opciones.body.se_entrega_de_a).toBeUndefined();
  });
});
