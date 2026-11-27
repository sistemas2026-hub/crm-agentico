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

describe('Instalaciones: Por activar (26/11/2026)', () => {
  it('la pestaña lee las instalaciones por activar y no la bandeja', async () => {
    apiRequest.mockReset();
    const instalaciones = [{ orden_id: 'o-1', numero: 21, espera: 'validacion', contrato: { estado: 'instalacion' } }];
    apiRequest.mockResolvedValue({ instalaciones });
    const d = /** @type {any} */ (await load(/** @type {any} */ ({
      cookies: { get: () => 'token' }, url: new URL('http://x/instalaciones?vista=por_activar')
    })));
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/instalaciones/por-activar/');
    expect(d.vista).toBe('por_activar');
    expect(d.instalaciones).toEqual(instalaciones);
  });

  it('APROBAR le pide al servidor que la active, para ESA orden', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ contrato: { estado: 'instalacion' } });
    const r = /** @type {any} */ (await actions.aprobarInstalacion(pedido({ orden: 'o-1' })));
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o-1/aprobar-instalacion/');
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'POST', body: {} });
    expect(r.hecho).toContain('activando');
  });

  it('si no se puede (409), lo dice tal cual', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue(Object.assign(new Error('x'), {
      status: 409, body: { detail: 'Todavía no hay una instalación en el proveedor: se está creando, espera un momento.' } }));
    const r = /** @type {any} */ (await actions.aprobarInstalacion(pedido({ orden: 'o-1' })));
    expect(r.status).toBe(409);
    expect(r.data.error).toContain('Todavía no hay una instalación');
  });

  it('VOLVER A PREPARAR el contrato del proveedor le llega a ESE contrato (26/11/2026)', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ contrato: { firma_proveedor: { estado: 'pedida' } } });
    const r = /** @type {any} */ (await actions.prepararContratoProveedor(
      pedido({ contrato: 'con-7', orden: 'o-1' })));
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/contratos/con-7/preparar-contrato-proveedor/');
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'POST', body: {} });
    expect(r.hecho).toContain('preparando');
  });

  it('...y si no se puede (409), lo dice tal cual; sin contrato no llama', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue(Object.assign(new Error('x'), {
      status: 409, body: { detail: 'Ahora no se puede pedir: o se está preparando, o ya está listo.' } }));
    const r = /** @type {any} */ (await actions.prepararContratoProveedor(
      pedido({ contrato: 'con-7', orden: 'o-1' })));
    expect(r.status).toBe(409);
    expect(r.data.error).toContain('Ahora no se puede pedir');
    apiRequest.mockReset();
    const sin = /** @type {any} */ (await actions.prepararContratoProveedor(pedido({ orden: 'o-1' })));
    expect(sin.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('DEVOLVER pide qué rehacer y por qué, y va por la validación de siempre', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});
    const f = new FormData();
    f.set('orden', 'o-1'); f.set('vuelta', '2'); f.append('requisito', 'foto_onu'); f.set('observacion', 'La foto salió movida');
    const r = /** @type {any} */ (await actions.devolverInstalacion(/** @type {any} */ ({
      request: { formData: async () => f }, cookies: { get: () => 'token' } })));
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o-1/validar/');
    expect(apiRequest.mock.calls[0][1].body).toEqual({
      decision: 'requerir_correccion', requisitos_a_corregir: ['foto_onu'], observacion: 'La foto salió movida' });
    expect(apiRequest.mock.calls[0][1].headers).toEqual({ 'Idempotency-Key': 'devolver|o-1|2' });
    expect(r.hecho).toContain('Devuelta');
  });

  it.each([
    [{ orden: 'o-1', observacion: 'x' }, 'Marca qué foto'],
    [{ orden: 'o-1', requisito: 'foto_onu' }, 'Escribe por qué']
  ])('devolver sin lo necesario no llega a la API (%o)', async (campos, texto) => {
    apiRequest.mockReset();
    const r = /** @type {any} */ (await actions.devolverInstalacion(pedido(campos)));
    expect(r.status).toBe(400);
    expect(r.data.error).toContain(texto);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
