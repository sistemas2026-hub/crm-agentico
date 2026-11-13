import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LA BANDEJA DE INSTALACIONES ES POR ÁREA (12/11/2026). Un 403 del backend
 * tiene que llegar a la página como «sin permiso», no como «no hay
 * solicitudes»: así se veía el mismo error el 08/09/2026, cuando la bandeja
 * vacía escondía un fallo de autenticación.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { leerBandeja, leerAjustesDecision, guardarAjustesDecision, reintentar } = await import(
  './solicitudes.js'
);

/** @param {number} status @param {any} body */
const fallo = (status, body) => Object.assign(new Error(body?.error || 'x'), { status, body });

beforeEach(() => {
  apiRequest.mockReset();
});

describe('Instalaciones: la bandeja', () => {
  it('trae las solicitudes y dice que hay permiso', async () => {
    apiRequest.mockResolvedValue({ solicitudes: [{ id: '1' }] });

    const r = await leerBandeja({}, '');

    expect(r).toEqual({ solicitudes: [{ id: '1' }], sinPermiso: false });
    expect(apiRequest.mock.calls[0][0]).toBe('/solicitudes/bandeja/');
  });

  it('un 403 llega como sin permiso, con el texto del backend', async () => {
    apiRequest.mockRejectedValue(
      fallo(403, { error: 'Decidir la factibilidad es de las áreas…', codigo: 'sin_permiso_instalaciones' })
    );

    const r = await leerBandeja({}, '');

    expect(r.sinPermiso).toBe(true);
    expect(r.solicitudes).toEqual([]);
    expect(r.error).toContain('áreas');
  });

  it('otro error no es falta de permiso', async () => {
    apiRequest.mockRejectedValue(fallo(502, { error: 'caído' }));

    const r = await leerBandeja({}, '');

    expect(r.sinPermiso).toBe(false);
    expect(r.error).toBe('caído');
  });

  it('el estado y las aprobadas por Dexter viajan en la consulta', async () => {
    apiRequest.mockResolvedValue({ solicitudes: [] });

    await leerBandeja({}, 'aprobada', { automatica: true });

    expect(apiRequest.mock.calls[0][0]).toBe('/solicitudes/bandeja/?estado=aprobada&automatica=1');
  });
});

describe('Instalaciones: reintentar', () => {
  it('pide al backend lo pendiente de ESA solicitud y devuelve lo que contesta', async () => {
    apiRequest.mockResolvedValue({ pendientes: [], aviso_cliente: { estado: 'enviado' } });

    const r = await reintentar({}, 'abc');

    expect(apiRequest.mock.calls[0][0]).toBe('/solicitudes/abc/reintentar/');
    expect(apiRequest.mock.calls[0][1].method).toBe('POST');
    expect(r.aviso_cliente.estado).toBe('enviado');
  });
});

describe('Instalaciones: quién decide', () => {
  it('lee los ajustes y no lanza si el backend falla', async () => {
    apiRequest.mockRejectedValue(fallo(500, { error: 'roto' }));

    expect(await leerAjustesDecision({})).toEqual({ error: 'roto' });
  });

  it('guarda con PUT y el cuerpo como objeto', async () => {
    apiRequest.mockResolvedValue({});

    await guardarAjustesDecision({}, { areas_que_deciden: ['tecnica'] });

    expect(apiRequest).toHaveBeenCalledWith(
      '/solicitudes/ajustes/decision/',
      { method: 'PUT', body: { areas_que_deciden: ['tecnica'] } },
      {}
    );
  });
});
