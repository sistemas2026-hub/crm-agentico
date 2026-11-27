import { describe, expect, it, vi } from 'vitest';

/**
 * CREDENCIALES: el nombre llega como lo acepta la base (26/11/2026). El
 * navegador llenaba la casilla del nombre con el usuario guardado y la base lo
 * rechazaba; ahora la de «agregar otra» tiene otro nombre de campo y el nombre
 * se pasa a MAYÚSCULAS con guion bajo antes de mandarlo.
 */
vi.mock('$lib/server/v2/tenant.js', () => ({
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'empresa-uno' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));

const { actions } = await import('./+page.server.js');

/** @param {Record<string, string>} campos @param {any} fetchFalso */
const pedido = (campos, fetchFalso) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({ request: { formData: async () => f }, locals: {}, fetch: fetchFalso });
};

describe('Credenciales: el nombre', () => {
  it.each([
    ['wisphub_web_usuario', 'WISPHUB_WEB_USUARIO'],
    ['wisphub web usuario', 'WISPHUB_WEB_USUARIO'],
    ['  Wisphub-Web-Clave ', 'WISPHUB_WEB_CLAVE']
  ])('«%s» viaja como %s, y el valor no se toca', async (escrito, esperado) => {
    const fetchFalso = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }));
    const r = /** @type {any} */ (await actions.guardar(pedido({ nombre_de_la_credencial: escrito, valor: 'Clave Con Mayus' }, fetchFalso)));
    const cuerpo = JSON.parse(fetchFalso.mock.calls[0][1].body);
    expect(cuerpo.nombre).toBe(esperado);
    expect(cuerpo.valor).toBe('Clave Con Mayus');
    expect(r.guardado).toBe(esperado);
  });

  it('el de cada fila (campo `nombre`) también se acepta', async () => {
    const fetchFalso = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }));
    await actions.guardar(pedido({ nombre: 'WISPHUB_API_KEY', valor: 'x' }, fetchFalso));
    expect(JSON.parse(fetchFalso.mock.calls[0][1].body).nombre).toBe('WISPHUB_API_KEY');
  });
});
