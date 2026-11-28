import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * AISLAMIENTO ENTRE EMPRESAS EN EL PROXY DEL FLUJO DE EVENTOS.
 *
 * Por qué existe, aunque `tenant.test.js` ya pruebe el ayudante
 * -------------------------------------------------------------
 * Aquella prueba afirma que `tenantDeLaSesion` resuelve bien y que ningún
 * archivo lee `PRIVATE_ASISTENTE_TENANT`. Las dos cosas son ciertas y no
 * alcanzan: **el ayudante puede estar perfecto y este endpoint pasarle otra
 * cosa al motor**. Es exactamente la falla que CLAUDE.md §6 describe — el
 * backend en verde y el salto siguiente perdiendo el dato — y que ya se cobró
 * dos veces el 29/09/2026 (`requiere_noc` y `estado_nuevo`).
 *
 * Acá se afirma sobre la URL que SALE hacia el motor, que es el único lugar
 * donde se decide de qué empresa son los datos que verá el navegador.
 *
 * Este proxy alimenta la oficina virtual con eventos reales. Servir el tenant
 * equivocado acá no es un error de pantalla: es mostrarle a una empresa la
 * operación de otra, evento por evento.
 */

const motorFetch = vi.fn();

vi.mock('$env/dynamic/private', () => ({
  env: {
    PRIVATE_ASISTENTE_URL: 'http://motor:8001',
    // Está a propósito: si el endpoint volviera a caer a la variable de
    // entorno, estas pruebas lo cazan en vez de pasar por casualidad.
    PRIVATE_ASISTENTE_TENANT: 'empresa-de-la-variable'
  }
}));

vi.mock('$lib/server/v2/motor-headers.js', () => ({
  headersMotor: () => ({ 'X-Interno': 'si' })
}));

/** El ayudante real resuelve `org.id -> slug` preguntándole al motor. */
vi.mock('$lib/server/v2/tenant.js', () => ({
  tenantDeLaSesion: async (/** @type {any} */ locals) => {
    const porOrg = { 'org-aaa': 'isp-norte', 'org-bbb': 'isp-sur' };
    const id = locals?.org?.id;
    return id ? (porOrg[/** @type {keyof typeof porOrg} */ (id)] ?? null) : null;
  }
}));

const { GET } = await import('./+server.js');

/** Una sesión de la empresa indicada. */
const sesion = (orgId) => ({ user: { id: 'u1' }, org: { id: orgId } });
const PETICION = { url: new URL('http://crm/api/eventos') };

beforeEach(() => {
  motorFetch.mockReset();
  motorFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ eventos: [], siguiente: '1.x', salto: false })
  });
});

/** El `tenant=` que viajó hacia el motor en la última llamada. */
function tenantPedido() {
  expect(motorFetch, 'el endpoint no llamó al motor').toHaveBeenCalled();
  const url = new URL(motorFetch.mock.calls[0][0]);
  return url.searchParams.get('tenant');
}

describe('dos ISPs no se ven entre sí', () => {
  it('cada sesión pide al motor el tenant de SU empresa', async () => {
    await GET({ ...PETICION, locals: sesion('org-aaa'), fetch: motorFetch });
    expect(tenantPedido()).toBe('isp-norte');

    motorFetch.mockClear();
    await GET({ ...PETICION, locals: sesion('org-bbb'), fetch: motorFetch });
    expect(tenantPedido()).toBe('isp-sur');
  });

  it('NUNCA pide el tenant de la variable de entorno', async () => {
    // El caso que convertiría la pantalla en un visor de empresas ajenas.
    await GET({ ...PETICION, locals: sesion('org-bbb'), fetch: motorFetch });
    expect(tenantPedido()).not.toBe('empresa-de-la-variable');
  });

  it('una empresa sin asistente NO recibe el de otra', async () => {
    // Falla cerrado: sin tenant propio no se sirve ninguno. Es la misma regla
    // que `app_backend` sin empresa fijada -> 0 filas, no todas.
    const r = await GET({ ...PETICION, locals: sesion('org-sin-asistente'), fetch: motorFetch });
    expect(r.status).toBe(500);
    expect(motorFetch).not.toHaveBeenCalled();
  });
});

describe('sin sesión no hay datos', () => {
  it('sin usuario responde 401 y no toca el motor', async () => {
    const r = await GET({ ...PETICION, locals: {}, fetch: motorFetch });
    expect(r.status).toBe(401);
    expect(motorFetch).not.toHaveBeenCalled();
  });

  it('con usuario pero sin organización tampoco', async () => {
    // El hueco sutil: autenticado no es lo mismo que pertenecer a una empresa.
    const r = await GET({ ...PETICION, locals: { user: { id: 'u1' } }, fetch: motorFetch });
    expect(r.status).toBe(500);
    expect(motorFetch).not.toHaveBeenCalled();
  });
});

describe('lo que el navegador puede pedir', () => {
  it('el limite viaja, porque el motor lo acota igual', async () => {
    const url = new URL('http://crm/api/eventos?limite=45');
    await GET({ url, locals: sesion('org-aaa'), fetch: motorFetch });
    expect(new URL(motorFetch.mock.calls[0][0]).searchParams.get('limite')).toBe('45');
  });

  it('el cliente NO puede elegir la empresa por query string', async () => {
    // Si `tenant` del query llegara a usarse, cualquiera leería a cualquiera
    // cambiando la barra de direcciones.
    const url = new URL('http://crm/api/eventos?tenant=isp-sur');
    await GET({ url, locals: sesion('org-aaa'), fetch: motorFetch });
    expect(tenantPedido()).toBe('isp-norte');
  });
});

describe('intentos deliberados de pedir la empresa de otro', () => {
  // La API debe rechazar CUALQUIER combinación donde la identidad autorizada y
  // la organización solicitada no coincidan. No alcanza con que el proxy use
  // el tenant de la sesión: hay que probar que el del cliente no se cuela por
  // ninguna vía, y que probarlo con una sola forma no basta.
  const ATAQUES = [
    ['?tenant=isp-sur', 'el slug de la otra empresa, tal cual'],
    ['?tenant=isp-sur&tenant=isp-norte', 'el parámetro repetido'],
    ['?TENANT=isp-sur', 'en mayúsculas, por si el servidor normaliza'],
    ['?tenant=isp-sur%00', 'con un byte nulo pegado'],
    ['?tenant=../isp-sur', 'con un salto de ruta'],
    ['?desde=1.00000000-0000-0000-0000-000000000000&tenant=isp-sur',
     'escondido detrás de un cursor válido']
  ];

  for (const [query, como] of ATAQUES) {
    it(`ignora ${como}`, async () => {
      const url = new URL(`http://crm/api/eventos${query}`);
      await GET({ url, locals: sesion('org-aaa'), fetch: motorFetch });
      // Lo que importa no es que falle: es QUÉ empresa se le pidió al motor.
      expect(tenantPedido()).toBe('isp-norte');
      motorFetch.mockClear();
    });
  }

  it('el cursor del cliente SÍ viaja, y es inofensivo', async () => {
    // El cursor no elige empresa: filtra hacia adelante DENTRO de la empresa
    // ya resuelta. Uno inventado devuelve menos eventos, nunca los de otra.
    const url = new URL('http://crm/api/eventos?desde=99.00000000-0000-0000-0000-000000000000');
    await GET({ url, locals: sesion('org-bbb'), fetch: motorFetch });
    const pedido = new URL(motorFetch.mock.calls[0][0]);
    expect(pedido.searchParams.get('tenant')).toBe('isp-sur');
    expect(pedido.searchParams.get('desde')).toBe('99.00000000-0000-0000-0000-000000000000');
  });

  it('dos sesiones seguidas NO se contaminan entre sí', async () => {
    // El caso que un mock perezoso dejaría pasar: que el tenant quede cacheado
    // entre peticiones y la segunda sesión herede el de la primera.
    const u = new URL('http://crm/api/eventos');
    await GET({ url: u, locals: sesion('org-aaa'), fetch: motorFetch });
    const primera = tenantPedido();
    motorFetch.mockClear();
    await GET({ url: u, locals: sesion('org-bbb'), fetch: motorFetch });
    const segunda = tenantPedido();
    expect(primera).toBe('isp-norte');
    expect(segunda).toBe('isp-sur');
  });
});
