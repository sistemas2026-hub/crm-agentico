import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LO QUE LA PERSONA CONFIRMA DE LA REVISIÓN (30/10/2026,
 * SPEC/objetivos/revision-del-cierre.md): aprobar y cerrar, o devolver.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { aprobarYCerrar, devolverAlTecnico } = await import('./revision-del-cierre.js');

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({ ticket_isp: { estado: 'ya_cerrado' } });
});

describe('aprobar y cerrar', () => {
  it('valida y después cierra, cada uno con su clave', async () => {
    const r = await aprobarYCerrar({ cookies: {} }, { orden: 'o 3', vuelta: 1, observacion: 'ok' });

    expect(apiRequest.mock.calls.map((c) => [c[0], c[1].headers['Idempotency-Key']])).toEqual([
      ['/campo/trabajos/o%203/validar/', 'aprobar|o 3|1'],
      ['/campo/trabajos/o%203/cerrar/', 'cerrar|o 3|1']
    ]);
    expect(r.ticketIsp).toEqual({ estado: 'ya_cerrado' });
  });

  it('si validar falla, no se intenta cerrar', async () => {
    apiRequest.mockRejectedValueOnce(new Error('409'));

    await expect(aprobarYCerrar({ cookies: {} }, { orden: 'o-3', vuelta: 1 })).rejects.toThrow('409');
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });
});

describe('devolver al técnico', () => {
  it('lleva qué rehacer y por qué', async () => {
    await devolverAlTecnico({ cookies: {} }, {
      orden: 'o-3', vuelta: 2, requisitos: ['foto_ont'], observacion: 'Falta la foto.'
    });

    expect(apiRequest.mock.calls[0][1]).toEqual({
      method: 'POST',
      body: { decision: 'requerir_correccion', requisitos_a_corregir: ['foto_ont'],
              observacion: 'Falta la foto.' },
      headers: { 'Idempotency-Key': 'devolver|o-3|2' }
    });
  });
});
