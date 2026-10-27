import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { _olvidarLasZonas, diaEn, zonaDeLaEmpresa } = await import('./hoy-de-la-empresa.js');

//  Lunes 26/10/2026 a las 20:30 de Bogotá = martes 27 a la 01:30 UTC.
const A_LAS_OCHO_Y_MEDIA = new Date('2026-10-27T01:30:00Z');
const cookies = /** @type {any} */ ({});

beforeEach(() => {
  apiRequest.mockReset();
  _olvidarLasZonas();
});

describe('el día en el reloj de la empresa', () => {
  it('después de las 19:00 de Bogotá sigue siendo hoy, no mañana', () => {
    expect(diaEn('America/Bogota', A_LAS_OCHO_Y_MEDIA)).toBe('2026-10-26');
    expect(diaEn('UTC', A_LAS_OCHO_Y_MEDIA)).toBe('2026-10-27');
  });

  it('una zona que no existe cae a UTC', () => {
    expect(diaEn('Marte/Olympus', A_LAS_OCHO_Y_MEDIA)).toBe('2026-10-27');
  });
});

describe('la zona de la empresa', () => {
  it('la lee una vez y la guarda diez minutos por empresa', async () => {
    apiRequest.mockResolvedValue({ timezone: 'America/Bogota' });
    const locals = { org: { id: 'a' } };

    expect(await zonaDeLaEmpresa(locals, cookies, 0)).toBe('America/Bogota');
    expect(await zonaDeLaEmpresa(locals, cookies, 9 * 60 * 1000)).toBe('America/Bogota');
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls[0][0]).toBe('/org/settings/');

    await zonaDeLaEmpresa(locals, cookies, 11 * 60 * 1000);
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it('otra empresa no usa la zona guardada de la primera', async () => {
    apiRequest.mockResolvedValueOnce({ timezone: 'America/Bogota' });
    apiRequest.mockResolvedValueOnce({ timezone: 'America/Mexico_City' });

    await zonaDeLaEmpresa({ org: { id: 'a' } }, cookies, 0);
    expect(await zonaDeLaEmpresa({ org: { id: 'b' } }, cookies, 0)).toBe('America/Mexico_City');
  });

  it('un fallo cae a UTC y no se guarda', async () => {
    apiRequest.mockRejectedValueOnce(new Error('caído'));
    apiRequest.mockResolvedValueOnce({ timezone: 'America/Bogota' });
    const locals = { org: { id: 'a' } };

    expect(await zonaDeLaEmpresa(locals, cookies, 0)).toBe('UTC');
    expect(await zonaDeLaEmpresa(locals, cookies, 1)).toBe('America/Bogota');
  });

  it('sin zona cargada, UTC como el backend', async () => {
    apiRequest.mockResolvedValue({ timezone: '' });
    expect(await zonaDeLaEmpresa({ org: { id: 'a' } }, cookies, 0)).toBe('UTC');
  });
});
