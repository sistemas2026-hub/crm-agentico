import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Variables de la empresa (12/11/2026). La cadena hasta el motor, con
 * `variables-empresa.js` REAL: solo se sustituyen el tenant de la sesión y
 * `fetch`. Lo que se afirma es lo que llega al motor y lo que recibe la página.
 */
vi.mock('$lib/server/v2/tenant.js', () => ({
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'empresa' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));

const { load, actions } = await import('./+page.server.js');

//  La forma EXACTA de GET /configuracion/variables (api.py::_usos_de_variables).
const DEL_MOTOR = {
  variables: { SMARTOLT_SUBDOMINIO: 'empresa', LINK_DE_PAGO: 'https://pagos.ejemplo' },
  usos: { SMARTOLT_SUBDOMINIO: ['consultar_estado_ont'] },
  faltan: { WISPHUB_BASE_URL: ['consultar_cliente'] }
};

/** @type {any[]} */
let pedidos;
/** @type {(url: string) => any} */
let responder;
beforeEach(() => {
  pedidos = [];
  responder = () => ({ ok: true, json: async () => structuredClone(DEL_MOTOR) });
});
const fetchFalso = vi.fn(async (/** @type {string} */ url, /** @type {any} */ init) => {
  pedidos.push({ url, init, cuerpo: init?.body ? JSON.parse(init.body) : null });
  return responder(url);
});

/** @param {Record<string, string>} campos @param {string} [rol] */
function evento(campos, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.append(k, v);
  return /** @type {any} */ ({ fetch: fetchFalso, request: { formData: async () => fd },
    locals: { profile: { role: rol } }, url: new URL('http://crm/settings/variables?nombre=wisphub_base_url') });
}

describe('variables de la empresa', () => {
  it('la página recibe variables, usos y faltantes tal cual, y la sugerida en mayúsculas', async () => {
    const d = /** @type {any} */ (await load(evento({})));
    expect(d.datos).toEqual(DEL_MOTOR);
    expect(d.sugerida).toBe('WISPHUB_BASE_URL');
    expect(pedidos[0].url).toBe('http://motor/configuracion/variables?tenant=empresa');
  });

  it('quien no es administrador no entra (la puerta es la carga, no el botón)', async () => {
    await expect(load(evento({}, 'USER'))).rejects.toMatchObject({ status: 303 });
    expect(pedidos).toHaveLength(0);
  });

  it('guardar manda el nombre normalizado en la ruta y el valor recortado', async () => {
    const r = /** @type {any} */ (await actions.guardar(evento({ nombre: ' wisphub_base_url ', valor: '  https://api.ejemplo  ' })));
    expect(r).toEqual({ guardada: 'WISPHUB_BASE_URL' });
    expect(pedidos[0].url).toBe('http://motor/configuracion/variables/WISPHUB_BASE_URL');
    expect(pedidos[0].init.method).toBe('PUT');
    expect(pedidos[0].cuerpo).toEqual({ tenant: 'empresa', valor: 'https://api.ejemplo' });
  });

  it('un nombre inválido o un valor vacío no llegan al motor', async () => {
    for (const [nombre, valor] of [['1MAL', 'x'], ['AB', 'x'], ['CON ESPACIO', 'x'], ['BIEN_NOMBRE', '  ']]) {
      const r = /** @type {any} */ (await actions.guardar(evento({ nombre, valor })));
      expect(r.status).toBe(400);
    }
    expect(pedidos).toHaveLength(0);
  });

  it('el rechazo del motor (p. ej. un valor con pinta de credencial) vuelve tal cual', async () => {
    responder = () => ({ ok: false, json: async () => ({ error: 'hay valores con pinta de credencial' }) });
    const r = /** @type {any} */ (await actions.guardar(evento({ nombre: 'ALGO_NUEVO', valor: 'sk-xxxxxxxx' })));
    expect(r.status).toBe(400);
    expect(r.data.error).toContain('credencial');
  });

  it('quitar manda DELETE con el tenant de la sesión', async () => {
    const r = /** @type {any} */ (await actions.borrar(evento({ nombre: 'LINK_DE_PAGO' })));
    expect(r).toEqual({ borrada: 'LINK_DE_PAGO' });
    expect(pedidos[0].url).toBe('http://motor/configuracion/variables/LINK_DE_PAGO?tenant=empresa');
    expect(pedidos[0].init.method).toBe('DELETE');
  });

  it('quien no es administrador no guarda ni quita', async () => {
    const a = /** @type {any} */ (await actions.guardar(evento({ nombre: 'ALGO', valor: 'x' }, 'USER')));
    const b = /** @type {any} */ (await actions.borrar(evento({ nombre: 'ALGO' }, 'BODEGA')));
    expect([a.status, b.status]).toEqual([403, 403]);
    expect(pedidos).toHaveLength(0);
  });
});
