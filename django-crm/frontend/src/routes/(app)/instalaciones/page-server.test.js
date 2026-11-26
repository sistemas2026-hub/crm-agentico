import { describe, expect, it, vi } from 'vitest';

/**
 * INSTALACIONES: volver a pedir que el cliente de un contrato se cree en el
 * proveedor (25/11/2026). La acción atraviesa formulario → acción → API: lo
 * que se afirma es a qué contrato le llega el pedido, no que la función exista.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { actions, load } = await import('./+page.server.js');

/** @param {Record<string, string>} campos */
const pedido = (campos) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({ request: { formData: async () => f }, cookies: { get: () => 'token' } });
};

describe('Instalaciones: crear al cliente en el proveedor', () => {
  it('el pedido le llega al contrato de ESA fila, no a la solicitud', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ contrato: { estado: 'firmado', alta: { estado: 'pedida' } } });

    const r = /** @type {any} */ (await actions.crearEnElIsp(pedido({ id: 'sol-1', contrato: 'con-9' })));

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/contratos/con-9/crear-en-el-isp/');
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'POST', body: {} });
    expect(r).toEqual({ altaPedida: true, id: 'sol-1', alta: { estado: 'pedida' }, estado: 'firmado' });
  });

  it('sin contrato no se pide nada', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.crearEnElIsp(pedido({ id: 'sol-1' })));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('GESTIÓN DICE QUE SÍ QUEDÓ: viaja el número del cliente, al contrato de esa fila', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ contrato: { estado: 'en_el_isp' } });

    const r = /** @type {any} */ (await actions.resolverAlta(
      pedido({ id: 'sol-1', contrato: 'con-9', quedo: 'si', id_cliente: ' 9020 ' })));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/contratos/con-9/resolver-alta/');
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'POST', body: { quedo_creado: true, id_cliente: '9020' } });
    expect(r).toEqual({ altaResuelta: true, id: 'sol-1', estado: 'en_el_isp' });
  });

  it('GESTIÓN DICE QUE NO QUEDÓ: viaja un «no» de verdad, sin número', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ contrato: { estado: 'firmado' } });

    await actions.resolverAlta(pedido({ id: 'sol-1', contrato: 'con-9', quedo: 'no', id_cliente: '123' }));

    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'POST', body: { quedo_creado: false } });
  });

  it('UN FORMULARIO A MEDIAS NO SE LEE COMO «NO QUEDÓ»', async () => {
    //  Sin decir sí o no, o con un «sí» sin número, no se manda nada: un «no»
    //  por descuido liberaría el contrato para crear OTRO cliente.
    for (const campos of [
      { id: 'sol-1', contrato: 'con-9' },
      { id: 'sol-1', contrato: 'con-9', quedo: 'quizas' },
      { id: 'sol-1', contrato: 'con-9', quedo: 'si', id_cliente: '   ' },
      { id: 'sol-1', quedo: 'no' }
    ]) {
      apiRequest.mockReset();
      const r = /** @type {any} */ (await actions.resolverAlta(pedido(campos)));
      expect(r.status).toBe(400);
      expect(apiRequest).not.toHaveBeenCalled();
    }
  });

  it('lo que el servidor rechaza llega a la pantalla con su motivo', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue(Object.assign(new Error('El cliente ya se está creando. Espera a que termine.'), { status: 409 }));

    const r = /** @type {any} */ (await actions.crearEnElIsp(pedido({ id: 'sol-1', contrato: 'con-9' })));

    expect(r.status).toBe(400);
    expect(r.data.error).toContain('ya se está creando');
    expect(r.data.id).toBe('sol-1');
  });
});

describe('Instalaciones: el contrato a nombre de otra persona (26/11/2026)', () => {
  it('a nombre de quién quedó llega a la página tal como lo dice el backend', async () => {
    apiRequest.mockReset();
    const contrato = {
      id: 'con-9', numero: 'C-2026-000301', estado: 'firmado', alta: { estado: null },
      otro_titular: true, documento_cambiado: false,
      titular: { nombre: 'Carlos Pérez Díaz', documento: 'Cédula de ciudadanía 72111222' }
    };
    apiRequest.mockResolvedValue({ solicitudes: [{ id: 'sol-1', contrato }] });

    const d = /** @type {any} */ (await load(/** @type {any} */ ({
      cookies: { get: () => 'token' }, url: new URL('http://x/instalaciones?estado=aprobada')
    })));

    expect(d.solicitudes[0].contrato.otro_titular).toBe(true);
    expect(d.solicitudes[0].contrato.titular).toEqual(contrato.titular);
  });
});
