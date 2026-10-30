import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LA CARGA DE PROGRAMACIÓN (28/10/2026): pide al backend lo publicado del día,
 * con el día de la URL o el de la empresa, y solo para quien gestiona.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2026-10-28' }));

const { load, actions } = await import('./+page.server.js');

describe('Programación: guardar de dónde y qué carga cada cuadrilla', () => {
  /** @param {string} rol */
  const pedido = (rol) => {
    const f = new FormData();
    f.set('kit:correctivo', 'k-1');
    f.set('bodega:c-1', '');
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol } }
    });
  };

  it('quien gestiona: viaja lo del formulario, vacío como «sin»', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});

    const r = /** @type {any} */ (await actions.material(pedido('SUPERVISOR')));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/material-del-dia/configuracion/');
    expect(apiRequest.mock.calls[0][1]).toEqual({
      method: 'PUT',
      // `apoyos` vacío: el formulario de la prueba no trae «se toma de apoyo» (30/10/2026).
      body: { kits: { correctivo: 'k-1' }, bodegas: { 'c-1': null }, apoyos: {} }
    });
    expect(r.hecho).toBeTruthy();
  });

  it('quien no gestiona no guarda nada', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.material(pedido('USER')));

    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

describe('Programación: la persona confirma lo que revisó el Supervisor (30/10/2026)', () => {
  /** @param {string} rol @param {Record<string, string | string[]>} campos */
  const pedido = (rol, campos) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(campos)) {
      for (const x of Array.isArray(v) ? v : [v]) f.append(k, x);
    }
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol } }
    });
  };

  it('aprobar: valida y después cierra, con la clave de la vuelta', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ ticket_isp: { estado: 'ya_cerrado' } });

    const r = /** @type {any} */ (await actions.aprobar(
      pedido('SUPERVISOR', { orden: 'o-3', vuelta: '2', veredicto: 'Se puede cerrar' })));

    expect(apiRequest.mock.calls.map((c) => c[0])).toEqual([
      '/campo/trabajos/o-3/validar/',
      '/campo/trabajos/o-3/cerrar/'
    ]);
    expect(apiRequest.mock.calls[0][1].body.decision).toBe('aprobar');
    expect(apiRequest.mock.calls[0][1].headers['Idempotency-Key']).toBe('aprobar|o-3|2');
    expect(apiRequest.mock.calls[1][1].headers['Idempotency-Key']).toBe('cerrar|o-3|2');
    expect(r.de).toBe('revision');
    expect(r.hecho).toBe('Aprobada y cerrada.');
  });

  it('aprobar: si el ticket del ISP no se cerró, lo dice', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ ticket_isp: { estado: 'no_cerrado' } });

    const r = /** @type {any} */ (await actions.aprobar(pedido('ADMIN', { orden: 'o-3', vuelta: '1' })));

    expect(r.hecho).toContain('El ticket del ISP no se pudo cerrar');
  });

  it('si validar falla, no se cierra', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue({ body: { detalle: 'Validacion no permitida' } });

    const r = /** @type {any} */ (await actions.aprobar(pedido('ADMIN', { orden: 'o-3', vuelta: '1' })));

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(r.status).toBe(400);
    expect(r.data.error).toBe('Validacion no permitida');
  });

  it('devolver: qué rehacer y por qué; sin eso no sale', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});

    const r = /** @type {any} */ (await actions.devolver(pedido('OPERACIONES', {
      orden: 'o-3', vuelta: '1', requisito: ['foto_ont', 'foto_caja'],
      observacion: 'Falta la foto de la ONT.'
    })));

    expect(apiRequest.mock.calls[0][1].body).toEqual({
      decision: 'requerir_correccion',
      requisitos_a_corregir: ['foto_ont', 'foto_caja'],
      observacion: 'Falta la foto de la ONT.'
    });
    expect(apiRequest.mock.calls[0][1].headers['Idempotency-Key']).toBe('devolver|o-3|1');
    expect(r.hecho).toContain('Devuelta al técnico');

    apiRequest.mockReset();
    const sinQue = /** @type {any} */ (await actions.devolver(pedido('ADMIN', { orden: 'o-3', observacion: 'x' })));
    const sinPorque = /** @type {any} */ (await actions.devolver(
      pedido('ADMIN', { orden: 'o-3', requisito: 'foto_ont', observacion: '  ' })));
    expect([sinQue.status, sinPorque.status]).toEqual([400, 400]);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('quien no gestiona no aprueba ni devuelve', async () => {
    apiRequest.mockReset();

    const a = /** @type {any} */ (await actions.aprobar(pedido('USER', { orden: 'o-3' })));
    const d = /** @type {any} */ (await actions.devolver(
      pedido('USER', { orden: 'o-3', requisito: 'x', observacion: 'y' })));

    expect([a.status, d.status]).toEqual([403, 403]);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

describe('Programación: lo que el Supervisor hace solo (30/10/2026)', () => {
  /** @param {string} rol @param {Record<string, string>} campos */
  const pedido = (rol, campos) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(campos)) f.set(k, v);
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol } }
    });
  };

  it('la casilla marcada es sí; desmarcada (no llega) es no; y no hay casilla de cerrar solo', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recordar_al_tecnico: true });

    const r = /** @type {any} */ (await actions.seguimiento(
      pedido('ADMIN', { recordar_al_tecnico: 'on', supervisor_cierra_solo: 'on' })));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/seguimiento/configuracion/');
    expect(apiRequest.mock.calls[0][1]).toEqual({ method: 'PUT', body: { recordar_al_tecnico: true } });
    expect(r.de).toBe('seguimiento');
    expect(r.hecho).toContain('le recuerda');

    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recordar_al_tecnico: false });
    const apagado = /** @type {any} */ (await actions.seguimiento(pedido('ADMIN', {})));
    expect(apiRequest.mock.calls[0][1].body).toEqual({ recordar_al_tecnico: false });
    expect(apagado.hecho).toContain('ya no le recuerda');
  });

  it('quien no gestiona no lo cambia', async () => {
    apiRequest.mockReset();
    const r = /** @type {any} */ (await actions.seguimiento(pedido('USER', { supervisor_cierra_solo: 'on' })));
    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

describe('Programación: la pestaña Cerradas (30/10/2026)', () => {
  /** @param {string} url @param {string} rol */
  const ctxDe = (url, rol) =>
    /** @type {any} */ ({ url: new URL(url), cookies: { get: () => 'token' }, locals: { org: { id: 'o' }, profile: { role: rol } } });

  it('pide las cerradas del rango, contado desde el día que se mira', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ cuentas: { cerradas: 0 }, ordenes: [] });

    const d = /** @type {any} */ (await load(ctxDe(
      'http://x/supervisor-noc/programacion?dia=2026-10-30&vista=cerradas&rango=ayer', 'ADMIN')));

    expect(d.vista).toBe('cerradas');
    expect(apiRequest.mock.calls.map((c) => c[0])).toEqual(['/campo/cerradas/?desde=2026-10-29&hasta=2026-10-29']);
    expect(d.cerradas).toEqual({ cuentas: { cerradas: 0 }, ordenes: [] });
  });

  it('un rango que no existe es hoy; y la vista Hoy no pide cerradas', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});
    const raro = /** @type {any} */ (await load(ctxDe('http://x/supervisor-noc/programacion?dia=2026-10-30&vista=cerradas&rango=x', 'ADMIN')));
    expect(raro.rango).toBe('hoy');
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/cerradas/?desde=2026-10-30&hasta=2026-10-30');

    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});
    const d = /** @type {any} */ (await load(ctxDe('http://x/supervisor-noc/programacion?dia=2026-10-30', 'ADMIN')));
    expect(d.vista).toBe('hoy');
    expect(apiRequest.mock.calls.some((c) => String(c[0]).includes('cerradas'))).toBe(false);
  });
});

const PUBLICADO = { fecha: '2026-10-28', cuadrillas: [], con_alguien_que_no_sale: [], esperan: [], cuentas: {} };

/** @param {string} url @param {string} rol */
const ctx = (url, rol) =>
  /** @type {any} */ ({
    url: new URL(url),
    cookies: { get: () => 'token' },
    locals: { org: { id: 'org-1' }, profile: { role: rol } }
  });

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue(PUBLICADO);
});

describe('Programación: la carga', () => {
  it('sin día en la URL pide el de la empresa', async () => {
    const d = /** @type {any} */ (await load(ctx('http://x/supervisor-noc/programacion', 'ADMIN')));

    expect(d.dia).toBe('2026-10-28');
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-28');
    expect(d.publicado).toEqual(PUBLICADO);
  });

  it('con día en la URL pide ese', async () => {
    await load(ctx('http://x/supervisor-noc/programacion?dia=2026-10-30', 'SUPERVISOR'));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-30');
  });

  it('un día mal escrito no viaja: usa el de la empresa', async () => {
    await load(ctx('http://x/supervisor-noc/programacion?dia=mañana', 'ADMIN'));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/dia-publicado/?fecha=2026-10-28');
  });

  it('quien no gestiona no pide nada', async () => {
    const d = /** @type {any} */ (await load(ctx('http://x/supervisor-noc/programacion', 'USER')));

    expect(d.puedeVer).toBe(false);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('si el backend no contesta, lo dice en vez de mostrar vacío', async () => {
    apiRequest.mockRejectedValue(new Error('caído'));

    const d = /** @type {any} */ (await load(ctx('http://x/supervisor-noc/programacion', 'ADMIN')));

    expect(d.publicado).toBe(null);
    expect(d.error).toBe(true);
  });
});
