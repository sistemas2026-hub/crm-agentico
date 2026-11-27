import { readFileSync } from 'node:fs';

import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LA CARGA DE PROGRAMACIÓN (28/10/2026): pide al backend lo publicado del día,
 * con el día de la URL o el de la empresa, y solo para quien gestiona.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2026-10-28' }));
//  De qué empresa es la sesión, para hablar con el motor (los rangos de IP).
//  Por defecto «no se sabe»: la carga no sale a ningún lado.
const tenant = { destinoDelAsistente: vi.fn(async () => null) };
vi.mock('$lib/server/v2/tenant.js', () => ({ destinoDelAsistente: (...a) => tenant.destinoDelAsistente(...a) }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));

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

describe('Programación: el contrato de instalación (25/11/2026)', () => {
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

  it('las costumbres de la empresa viajan al backend con los servidores', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ servidores: [{ id_zona: 20053, nombre: 'CORTE 15' }], texto_condiciones: 'x' });

    const r = /** @type {any} */ (await actions.contrato(pedido('SUPERVISOR', {
      servidor_id_0: '20053', servidor_nombre_0: 'CORTE 15', nit: '900',
      texto_condiciones: 'x', datos_en_mayusculas: 'on', digitos_del_telefono: '10'
    })));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/contrato/configuracion/');
    expect(apiRequest.mock.calls[0][1]).toEqual({
      method: 'PUT',
      body: {
        nit: '900', servidores: [{ id_zona: 20053, nombre: 'CORTE 15' }], texto_condiciones: 'x',
        abreviaturas_de_direccion: [],
        //  La casilla que NO se marcó viaja como false: si no viajara, una
        //  costumbre encendida no se podría apagar desde la pantalla.
        datos_en_mayusculas: true, barrio_en_la_direccion: false, digitos_del_telefono: 10,
        //  Y el interruptor de crear en el proveedor, que no se marcó: false.
        crear_en_el_isp: false,
        //  Y el de activar la ONU (26/11/2026), tampoco marcado: false.
        activar_onu: false,
        //  Y los de validar la instalación y firmar en el proveedor (26/11/2026).
        validar_antes_de_activar: false,
        firma_en_el_proveedor: false
      }
    });
    expect(r.hecho).toBeTruthy();
  });

  it('UN FORMULARIO VACÍO NO BORRA LOS SERVIDORES QUE HAY (26/11/2026)', async () => {
    //  Ese día la pantalla quedó en blanco después de guardar y el siguiente
    //  guardado se llevó los servidores, las VLAN y las reglas.
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ servidores: [{ id_zona: 1 }, { id_zona: 2 }, { id_zona: 3 }] });

    const r = /** @type {any} */ (await actions.contrato(pedido('ADMIN', { nit: '', texto_condiciones: '' })));

    expect(r.status).toBe(400);
    expect(r.data.error).toContain('hay 3 cargados');
    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls[0][1]?.method ?? 'GET').toBe('GET');
  });

  it('una empresa SIN servidores todavía sí puede guardar sin servidores', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValueOnce({ servidores: [] }).mockResolvedValueOnce({ servidores: [] });

    const r = /** @type {any} */ (await actions.contrato(pedido('ADMIN', { nit: '900' })));

    expect(apiRequest.mock.calls[1][1]?.method).toBe('PUT');
    expect(r.hecho).toContain('sin servidores');
  });

  it('si no se puede leer lo guardado, un formulario sin servidores no se guarda', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 500 }));

    const r = /** @type {any} */ (await actions.contrato(pedido('ADMIN', { nit: '900' })));

    expect(r.status).toBe(400);
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });

  it('quien no gestiona no cambia el contrato', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.contrato(pedido('USER', { datos_en_mayusculas: 'on' })));

    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

describe('Programación: los rangos de IP de cada servidor (25/11/2026)', () => {
  /** @param {string} rol @param {Record<string, string>} campos @param {any} fetchFalso */
  const pedido = (rol, campos, fetchFalso) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(campos)) f.set(k, v);
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol } },
      fetch: fetchFalso
    });
  };

  /** Un motor de mentira: contesta lo guardado y anota lo que le mandan. */
  const motor = (guardados = /** @type {any[]} */ ([])) => {
    /** @type {Array<{ url: string, metodo: string, cuerpo: any }>} */
    const pedidos = [];
    const fetchFalso = vi.fn(async (/** @type {string} */ url, /** @type {any} */ opciones = {}) => {
      const cuerpo = opciones.body ? JSON.parse(opciones.body) : null;
      pedidos.push({ url, metodo: opciones.method ?? 'GET', cuerpo });
      const datos = (opciones.method ?? 'GET') === 'GET' ? { pools: guardados } : { pools: cuerpo?.pools ?? [] };
      return { ok: true, json: async () => datos };
    });
    return { pedidos, fetchFalso };
  };

  it('viajan al motor los del formulario, sin borrar el rango de otra zona', async () => {
    tenant.destinoDelAsistente.mockResolvedValue({ baseUrl: 'http://motor', tenant: 'empresa-uno' });
    const { pedidos, fetchFalso } = motor([{ zona_id: 99, zona_nombre: 'OTRA', prefijos: ['10.9.9.'] }]);

    const r = /** @type {any} */ (await actions.rangos(pedido('SUPERVISOR', {
      rango_zona_0: '20049', rango_nombre_0: 'CORTE 30', rango_prefijos_0: '172.16.9., 172.16.10.'
    }, fetchFalso)));

    const put = pedidos.find((p) => p.metodo === 'PUT');
    expect(put?.url).toBe('http://motor/configuracion/rangos-de-ip');
    expect(put?.cuerpo).toEqual({
      tenant: 'empresa-uno',
      pools: [
        { zona_id: 20049, zona_nombre: 'CORTE 30', prefijos: ['172.16.9.', '172.16.10.'] },
        { zona_id: 99, zona_nombre: 'OTRA', prefijos: ['10.9.9.'] }
      ],
      //  La casilla no se marcó: viaja como «no», para poder apagarla.
      contar_ip_mal_escritas: false
    });
    expect(r.hecho).toContain('2 servidores con rangos');
  });

  it('LA CASILLA DE LAS IP MAL ESCRITAS, marcada, viaja como sí', async () => {
    tenant.destinoDelAsistente.mockResolvedValue({ baseUrl: 'http://motor', tenant: 'empresa-uno' });
    const { pedidos, fetchFalso } = motor([]);

    await actions.rangos(pedido('ADMIN', {
      rango_zona_0: '20049', rango_prefijos_0: '172.16.9.', contar_ip_mal_escritas: 'on'
    }, fetchFalso));

    expect(pedidos.find((p) => p.metodo === 'PUT')?.cuerpo?.contar_ip_mal_escritas).toBe(true);
  });

  it('si el motor no contesta al leer, NO se guarda nada (se podrían borrar rangos)', async () => {
    tenant.destinoDelAsistente.mockResolvedValue({ baseUrl: 'http://motor', tenant: 'empresa-uno' });
    const fetchFalso = vi.fn(async () => ({ ok: false, json: async () => ({}) }));

    const r = /** @type {any} */ (await actions.rangos(pedido('ADMIN', { rango_zona_0: '1', rango_prefijos_0: '' }, fetchFalso)));

    expect(r.status).toBe(400);
    expect(fetchFalso.mock.calls.every((/** @type {any} */ c) => (c[1]?.method ?? 'GET') === 'GET')).toBe(true);
  });

  it('UN FORMULARIO VACÍO NO BORRA LOS RANGOS QUE HAY (26/11/2026)', async () => {
    tenant.destinoDelAsistente.mockResolvedValue({ baseUrl: 'http://motor', tenant: 'empresa-uno' });
    const { pedidos, fetchFalso } = motor([
      { zona_id: 20049, zona_nombre: 'CORTE 30', prefijos: ['172.16.9.'] },
      { zona_id: 20053, zona_nombre: 'CORTE 15', prefijos: ['172.16.7.'] }
    ]);

    const r = /** @type {any} */ (await actions.rangos(pedido('ADMIN', {
      rango_zona_0: '20049', rango_prefijos_0: '', rango_zona_1: '20053', rango_prefijos_1: ''
    }, fetchFalso)));

    expect(r.status).toBe(400);
    expect(r.data.error).toContain('sin ningún rango');
    expect(pedidos.some((p) => p.metodo === 'PUT')).toBe(false);
  });

  it('vaciar el rango de UN servidor, con los otros escritos, sí se guarda', async () => {
    tenant.destinoDelAsistente.mockResolvedValue({ baseUrl: 'http://motor', tenant: 'empresa-uno' });
    const { pedidos, fetchFalso } = motor([
      { zona_id: 20049, zona_nombre: 'CORTE 30', prefijos: ['172.16.9.'] },
      { zona_id: 20053, zona_nombre: 'CORTE 15', prefijos: ['172.16.7.'] }
    ]);

    await actions.rangos(pedido('ADMIN', {
      rango_zona_0: '20049', rango_prefijos_0: '', rango_zona_1: '20053', rango_prefijos_1: '172.16.7.'
    }, fetchFalso));

    expect(pedidos.find((p) => p.metodo === 'PUT')?.cuerpo?.pools).toEqual([
      { zona_id: 20049, zona_nombre: '', prefijos: [] },
      { zona_id: 20053, zona_nombre: '', prefijos: ['172.16.7.'] }
    ]);
  });

  it('quien no gestiona no guarda ni lee el proveedor', async () => {
    const fetchFalso = vi.fn();
    const r1 = /** @type {any} */ (await actions.rangos(pedido('USER', { rango_zona_0: '1' }, fetchFalso)));
    const r2 = /** @type {any} */ (await actions.leerOcupacion(pedido('USER', {}, fetchFalso)));
    expect(r1.status).toBe(403);
    expect(r2.status).toBe(403);
    expect(fetchFalso).not.toHaveBeenCalled();
  });

  it('leer la ocupación llama a la ruta que recorre el proveedor, y dice qué leyó', async () => {
    tenant.destinoDelAsistente.mockResolvedValue({ baseUrl: 'http://motor', tenant: 'empresa-uno' });
    const fetchFalso = vi.fn(async () => ({
      ok: true, json: async () => ({ completa: true, leidos: 7711, direcciones_tomadas: 7500 })
    }));

    const r = /** @type {any} */ (await actions.leerOcupacion(pedido('OPERACIONES', {}, fetchFalso)));

    expect(fetchFalso.mock.calls[0][0]).toBe('http://motor/configuracion/ocupacion-ip/sincronizar');
    expect(JSON.parse(fetchFalso.mock.calls[0][1].body)).toEqual({ tenant: 'empresa-uno' });
    expect(r.hecho).toContain('7711');
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

  it('cerrar la aprobada: solo el cierre, con la clave de la vuelta', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.cerrar(pedido('ADMIN', { orden: 'o-3', vuelta: '1' })));
    expect(apiRequest.mock.calls.map((c) => c[0])).toEqual(['/campo/trabajos/o-3/cerrar/']);
    expect(apiRequest.mock.calls[0][1].headers['Idempotency-Key']).toBe('cerrar|o-3|1');
    expect(r.hecho).toContain('Cerradas');
    apiRequest.mockReset();
    expect((/** @type {any} */ (await actions.cerrar(pedido('USER', { orden: 'o-3' })))).status).toBe(403);
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

  //  CADA CUÁNTO INSISTE (11/11/2026). El campo nuevo entra por la misma
  //  pantalla, y lo que se mide acá es el borde que el backend rechaza: un
  //  `<input type="number">` pone TEXTO en el FormData y el PUT exige un
  //  entero. Un test que mandara 15 como número no vería ese bug.
  it('los minutos viajan como número, no como el texto del formulario', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recordar_al_tecnico: true, repetir_recordatorio_cada_minutos: 15 });

    await actions.seguimiento(pedido('ADMIN', { recordar_al_tecnico: 'on', repetir_recordatorio_cada_minutos: '15' }));

    const cuerpo = apiRequest.mock.calls[0][1].body;
    expect(cuerpo.repetir_recordatorio_cada_minutos).toBe(15);
    expect(typeof cuerpo.repetir_recordatorio_cada_minutos).toBe('number');
  });

  it('el 0 sí viaja: es «avisar una sola vez», no un campo vacío', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recordar_al_tecnico: true, repetir_recordatorio_cada_minutos: 0 });

    await actions.seguimiento(pedido('ADMIN', { recordar_al_tecnico: 'on', repetir_recordatorio_cada_minutos: '0' }));

    expect(apiRequest.mock.calls[0][1].body.repetir_recordatorio_cada_minutos).toBe(0);
  });

  //  LA DIFERENCIA ENTRE «VACÍO» Y «CERO» ES EL BUG QUE ESTO EVITA: si el
  //  campo vacío viajara, llegaría como 0 y APAGARÍA la insistencia de una
  //  empresa que solo quería tocar la casilla.
  it('un campo vacío o con letras no se manda, para no pisar el valor guardado', async () => {
    for (const malo of ['', '   ', 'quince', '7.5']) {
      apiRequest.mockReset();
      apiRequest.mockResolvedValue({ recordar_al_tecnico: true, repetir_recordatorio_cada_minutos: 15 });

      await actions.seguimiento(pedido('ADMIN', { recordar_al_tecnico: 'on', repetir_recordatorio_cada_minutos: malo }));

      const cuerpo = apiRequest.mock.calls[0][1].body;
      expect(Object.keys(cuerpo)).toEqual(['recordar_al_tecnico']);
    }
  });

  it('el mensaje de guardado dice con qué cadencia quedó', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recordar_al_tecnico: true, repetir_recordatorio_cada_minutos: 20 });
    const conInsistencia = /** @type {any} */ (await actions.seguimiento(
      pedido('ADMIN', { recordar_al_tecnico: 'on', repetir_recordatorio_cada_minutos: '20' })));
    expect(conInsistencia.hecho).toContain('cada 20 minutos');

    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ recordar_al_tecnico: true, repetir_recordatorio_cada_minutos: 0 });
    const unaSolaVez = /** @type {any} */ (await actions.seguimiento(
      pedido('ADMIN', { recordar_al_tecnico: 'on', repetir_recordatorio_cada_minutos: '0' })));
    expect(unaSolaVez.hecho).toContain('una sola vez');
    expect(unaSolaVez.hecho).not.toContain('cada 0');
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

  it('el HOY DE LA EMPRESA viaja, y es el mismo con o sin día en la URL', async () => {
    //  EL DEFECTO (01/11/2026): el mapa se dibujaba solo si el día que se
    //  mira es hoy, y la pantalla lo comparaba contra «America/Bogota»
    //  escrito a mano en el navegador. Con el reloj del navegador en otra
    //  zona --o con otra empresa-- los dos días no coincidían y el mapa NO
    //  APARECÍA NUNCA, sin ningún error. El servidor ya sabe cuál es el día
    //  de la empresa: lo manda, y la pantalla compara contra eso.
    const sinDia = /** @type {any} */ (
      await load(ctx('http://x/supervisor-noc/programacion', 'ADMIN'))
    );
    const conOtroDia = /** @type {any} */ (
      await load(ctx('http://x/supervisor-noc/programacion?dia=2026-10-30', 'ADMIN'))
    );

    expect(sinDia.hoy).toBe('2026-10-28');
    expect(sinDia.dia).toBe(sinDia.hoy);
    //  Mirando otro día, `hoy` NO cambia: es lo que distingue «hoy» de «lo
    //  que estoy mirando», que es justo lo que decide si se dibuja el mapa.
    expect(conOtroDia.hoy).toBe('2026-10-28');
    expect(conOtroDia.dia).toBe('2026-10-30');
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

  it('los seis pedidos salen A LA VEZ: ninguno espera a que otro conteste', async () => {
    //  21/11/2026, el usuario: «cuando se recarga demora en salir». La marca
    //  de agua y el contrato se pedían después de los otros cuatro, uno
    //  detrás del otro: dos viajes más al backend, en fila, antes de dibujar.
    //
    //  SE MIDE CON EL BACKEND SIN CONTESTAR. Afirmar solo «se pidieron los
    //  seis» pasaba igual con el código de antes: en fila también terminan
    //  pidiéndose todos.
    /** @type {Array<(v: any) => void>} */
    const soltar = [];
    apiRequest.mockImplementation(() => new Promise((ok) => soltar.push(ok)));

    const carga = load(ctx('http://x/supervisor-noc/programacion', 'ADMIN'));
    await new Promise((ok) => setTimeout(ok, 0));

    const pedidos = apiRequest.mock.calls.map((c) => c[0]);
    expect(pedidos).toHaveLength(6);
    expect(pedidos).toContain('/campo/marca-de-agua/configuracion/');
    expect(pedidos).toContain('/campo/contrato/configuracion/');

    soltar.forEach((ok) => ok({ dato: 1 }));
    const d = /** @type {any} */ (await carga);
    expect(d.marcaDeAgua).toEqual({ dato: 1 });
    expect(d.contrato).toEqual({ dato: 1 });
  });
});

/**
 * MOVER LA ORDEN A OTRO TÉCNICO (14/11/2026).
 *
 * Lo que se mide acá es lo que SALE hacia el backend —a qué URL, con qué
 * cuerpo— y lo que NO sale cuando falta algo. El efecto del otro lado
 * (`campo/services/despacho.py::asignar`) ya tiene sus pruebas en Python:
 * repetirlas acá sería medir dos veces lo mismo y ninguna vez esta capa.
 */
describe('Programación: mover una orden a otro técnico', () => {
  /** @param {{rol?: string, profile?: string, motivo?: string}} d */
  const pedido = ({ rol = 'SUPERVISOR', profile = 'p-bb', motivo = 'Se enfermó' } = {}) => {
    const f = new FormData();
    f.set('orden', 'o-1');
    f.set('profile', profile);
    f.set('motivo', motivo);
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol } }
    });
  };

  it('viaja el id de la persona y el motivo, al endpoint de la orden', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({});

    const r = /** @type {any} */ (await actions.mover(pedido()));

    //  `/mover/`, NO `/asignar/`: el segundo deja al anterior con acceso de
    //  escritura sobre la orden (medido el 14/11/2026). Que esta linea diga
    //  cual de los dos es lo unico que impide volver al endpoint equivocado.
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o-1/mover/');
    expect(apiRequest.mock.calls[0][1]).toEqual({
      method: 'POST',
      body: { profile_id: 'p-bb', motivo: 'Se enfermó' }
    });
    expect(r.hecho).toBeTruthy();
    //  DE QUE ORDEN es el resultado: la tarjeta lo compara contra el suyo
    //  para no sacar el mismo mensaje en las treinta.
    expect(r.orden).toBe('o-1');
  });

  //  EL MENSAJE NO AFIRMA EL AVISO: lo lee de la respuesta. `avisar_asignacion`
  //  sale solo si la persona es nueva en la orden, y devolverle la orden a
  //  quien la tenia antes no manda nada. Decirle al Supervisor que si,
  //  cuando no, lo deja esperando una llamada que nadie va a recibir.
  it('el mensaje dice si el aviso salió o no', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ resultado: 'movida', aviso: true });
    const con = /** @type {any} */ (await actions.mover(pedido()));

    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ resultado: 'movida', aviso: false });
    const sin = /** @type {any} */ (await actions.mover(pedido()));

    expect(con.hecho).toContain('Le llegó el aviso');
    expect(sin.hecho).toContain('No le llega aviso');
  });

  it('mover a quien ya la tenía lo dice, en vez de decir que la movió', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ resultado: 'sin_cambios', aviso: false });

    const r = /** @type {any} */ (await actions.mover(pedido()));

    expect(r.hecho).toContain('ya la tenía');
  });

  //  SIN MOTIVO NO SALE, aunque el backend lo acepte vacío: el evento
  //  `reasignacion` lo guarda y es lo único que después explica por qué un
  //  trabajo cambió de manos.
  it('sin motivo no se mueve nada', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.mover(pedido({ motivo: '   ' })));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('sin a quién pasársela tampoco', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.mover(pedido({ profile: '' })));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('quien no gestiona no mueve nada', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.mover(pedido({ rol: 'USER' })));

    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

/**
 * QUE LA PANTALLA LO ALIMENTE (14/11/2026).
 *
 * `OrdenDelDia` dibuja el control solo si recibe `aQuienMover`, y la lista la
 * arma esta página. Si esa línea se cae, el componente sigue en verde con sus
 * nueve pruebas y el control no aparece nunca: es exactamente el «código
 * construido no es código que corre» de CLAUDE.md §6.
 *
 * SE LEE EL FUENTE porque no hay jsdom en este proyecto —toda prueba de
 * componente renderiza en el servidor— y una página entera con su `load` no
 * se monta así. Es una prueba de cableado, no de comportamiento, y eso es
 * justo lo que falta cubrir.
 */
describe('Programación: el control de mover llega dibujado', () => {
  it('la página le pasa la lista de destinos a cada tarjeta', () => {
    const fuente = readFileSync(
      new URL('./+page.svelte', import.meta.url), 'utf-8');

    //  Desde el 24/11/2026 la tarjeta va dentro de una fila: la página se lo
    //  pasa a las filas y las filas a la tarjeta. Se miden los dos tramos.
    const filas = readFileSync(
      new URL('../../../../lib/supervisor/OrdenesDeLaCuadrilla.svelte', import.meta.url), 'utf-8');

    expect(fuente).toMatch(/<OrdenesDeLaCuadrilla[^>]*\{aQuienMover\}/);
    expect(filas).toMatch(/<OrdenDelDia[^>]*\{aQuienMover\}/);
    expect(fuente).toContain('aQuienSeLePuedeMover(publicado?.cuadrillas)');
    //  Y `form`, o la tarjeta no tiene con que mostrar si la orden se movio
    //  o por que no (14/11/2026).
    expect(fuente).toMatch(/<OrdenesDeLaCuadrilla[^>]*\{form\}/);
    expect(filas).toMatch(/<OrdenDelDia[^>]*\{form\}/);
  });
});


/**
 * DEVOLVER AL TÉCNICO UNA ORDEN DETENIDA (20/11/2026, OT #328).
 *
 * El backend ya sabía destrabar y desde esta pantalla nadie lo llamaba. Acá se
 * mide esta capa: qué viaja, a dónde, y qué se le dice a quien apretó.
 */
describe('Programación: devolver al técnico una orden detenida', () => {
  /** @param {{rol?: string, aclaracion?: string}} d */
  const pedido = ({ rol = 'SUPERVISOR', aclaracion = 'Ya abrieron el portón' } = {}) => {
    const f = new FormData();
    f.set('orden', 'o-1');
    f.set('aclaracion', aclaracion);
    return /** @type {any} */ ({
      request: { formData: async () => f },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol } }
    });
  };

  it('la aclaración viaja como lo que se hizo, al endpoint del bloqueo', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ aviso: true, estado_operativo: 'en_sitio' });

    const r = /** @type {any} */ (await actions.destrabar(pedido()));

    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o-1/bloqueo/resolver/');
    expect(apiRequest.mock.calls[0][1].method).toBe('POST');
    expect(apiRequest.mock.calls[0][1].body).toEqual({
      que_se_hizo: 'Ya abrieron el portón',
      resuelto_por_rol: 'coordinacion'
    });
    //  SIN `volver_a`: el destino lo guardó el bloqueo al abrirse.
    expect(apiRequest.mock.calls[0][1].body).not.toHaveProperty('volver_a');
    expect(r.orden).toBe('o-1');
    expect(r.hecho).toContain('Le llega el aviso');
  });

  //  NO AFIRMA EL AVISO: lo lee de la respuesta.
  it('si no había a quién avisarle, lo dice', async () => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ aviso: false, estado_operativo: 'en_sitio' });

    const r = /** @type {any} */ (await actions.destrabar(pedido()));

    expect(r.hecho).toContain('No salió aviso');
  });

  it('sin aclaración no se destraba nada', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.destrabar(pedido({ aclaracion: '   ' })));

    expect(r.status).toBe(400);
    expect(r.data.orden).toBe('o-1');
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('el motivo del rechazo del servidor llega a la tarjeta', async () => {
    apiRequest.mockReset();
    apiRequest.mockRejectedValue({ status: 409, body: {
      detalle: 'Esta orden no tiene ningún bloqueo abierto.' } });

    const r = /** @type {any} */ (await actions.destrabar(pedido()));

    expect(r.status).toBe(400);
    expect(r.data.error).toContain('ningún bloqueo abierto');
    expect(r.data.orden).toBe('o-1');
  });

  it('quien no gestiona no destraba', async () => {
    apiRequest.mockReset();

    const r = /** @type {any} */ (await actions.destrabar(pedido({ rol: 'USER' })));

    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
