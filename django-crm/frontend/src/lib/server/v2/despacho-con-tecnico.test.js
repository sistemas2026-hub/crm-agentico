import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * DESPACHO ES LO QUE FALTA (28/10/2026): lo que ya tiene técnico no viene por
 * defecto --está en Programación--, se cuenta, y se trae solo si se pide.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { leerCasosDespachables } = await import('./despacho.js');

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({ casos: [], total: 0, con_tecnico: 3 });
});

describe('Despacho: lo que ya tiene técnico', () => {
  it('por defecto no lo pide, y trae cuántos son', async () => {
    const r = await leerCasosDespachables({ cookies: {} }, false, {});

    expect(apiRequest.mock.calls[0][0]).not.toContain('con_tecnico');
    expect(r.conTecnico).toBe(3);
  });

  it('pidiéndolo, lo trae', async () => {
    await leerCasosDespachables({ cookies: {} }, false, { conTecnico: true });

    expect(apiRequest.mock.calls[0][0]).toContain('con_tecnico=1');
  });

  it('si el backend no contesta, la cuenta es cero y se marca el error', async () => {
    apiRequest.mockRejectedValue(new Error('caído'));

    const r = await leerCasosDespachables({ cookies: {} }, false, {});

    expect(r.conTecnico).toBe(0);
    expect(r.error).toBe(true);
  });
});
