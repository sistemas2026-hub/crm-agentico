import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * QUE EL PROXY LE PASE A 'apiRequest' ALGO DE DONDE PUEDA SACAR EL JWT
 * =====================================================================
 *
 * EL DEFECTO QUE ESTO VIENE A FIJAR  --  medido el 05/10/2026 en produccion
 * -------------------------------------------------------------------------
 * La burbuja se desplego y la primera pregunta devolvio
 *
 *     "Organization context is required. Please login again."
 *
 * 'apiRequest(endpoint, options, locals)' resuelve el token asi:
 *
 *     const cookies = locals.cookies || locals;
 *     const accessToken = cookies?.get?.('jwt_access');
 *
 * En un '+server.js' el evento trae 'cookies' APARTE de 'locals', y
 * 'hooks.server.js' nunca lo copia adentro. El fallback agarraba 'locals',
 * '.get' no existia, no salia 'Authorization' y Django respondia 403. El
 * mensaje mandaba a revisar el login, que estaba bien.
 *
 * POR QUE SE AFIRMA SOBRE EL TOKEN Y NO SOBRE LA FORMA DE LA LLAMADA
 * -------------------------------------------------------------------
 * Una prueba que dijera "se llamo con { cookies }" pasaria igual si manana
 * 'apiRequest' cambiara de donde saca el token. Lo que importa es el EFECTO:
 * que de lo que se le pasa se pueda extraer el JWT con la MISMA expresion
 * que usa 'apiRequest'. Por eso el doble la reproduce textualmente.
 */

const TOKEN = 'jwt-de-prueba';

/** Lo que 'apiRequest' hace para sacar el token, copiado tal cual. */
function tokenQueVeria(tercerArgumento) {
  const cookies = tercerArgumento?.cookies || tercerArgumento;
  return cookies?.get?.('jwt_access');
}

const apiRequest = vi.fn();
const tenantDeLaSesion = vi.fn();

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor:5000' } }));
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (e = {}) => e }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: (...a) => tenantDeLaSesion(...a) }));

const { POST, GET } = await import('./+server.js');

/** El `cookies` que SvelteKit entrega en un +server.js. */
const cookies = { get: (n) => (n === 'jwt_access' ? TOKEN : undefined) };
/** Lo que hooks.server.js deja en locals: user y org, NUNCA cookies. */
const locals = { user: { id: 'u-7' }, org: { id: 'org-1' }, tenant: 'rapilink' };

function evento(cuerpo = { mensaje: 'hola' }) {
  return {
    request: { json: async () => cuerpo },
    locals: structuredClone(locals),
    cookies,
    fetch: vi.fn(async () => ({ ok: true, json: async () => ({ respuesta: 'listo' }) }))
  };
}

beforeEach(() => {
  apiRequest.mockReset();
  tenantDeLaSesion.mockReset().mockResolvedValue('rapilink');
  apiRequest.mockResolvedValue({ user_obj: { id: 'p-9', name: 'Ana' } });
});

describe('POST — la identidad llega autenticada', () => {
  it('de lo que se le pasa a apiRequest SE PUEDE sacar el JWT', async () => {
    await POST(evento());
    expect(apiRequest).toHaveBeenCalled();
    for (const llamada of apiRequest.mock.calls) {
      expect(tokenQueVeria(llamada[2])).toBe(TOKEN);
    }
  });

  it('lo que recibe tiene un .get llamable; locals no lo tiene', async () => {
    //  La version anterior de esta prueba afirmaba 'llamada[2] !== locals' y
    //  NO servia: el evento clona 'locals', asi que la desigualdad se cumplia
    //  igual con el bug puesto. Sobrevivia intacta a la conducta que debia
    //  cazar. Se afirma sobre la capacidad, que es lo que 'apiRequest' usa.
    expect(typeof locals.get).toBe('undefined');
    expect(tokenQueVeria(locals)).toBeUndefined();
    await POST(evento());
    for (const llamada of apiRequest.mock.calls) {
      const fuente = llamada[2]?.cookies || llamada[2];
      expect(typeof fuente?.get).toBe('function');
    }
  });

  it('consulta el perfil para resolver profile_id del lado del servidor', async () => {
    await POST(evento());
    expect(apiRequest.mock.calls.some((c) => c[0] === '/profile/')).toBe(true);
  });

  it('manda al motor el profile_id resuelto, no uno del cuerpo', async () => {
    const ev = evento({ mensaje: 'hola', profile_id: 'INTRUSO' });
    await POST(ev);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.profile_id).toBe('p-9');
  });

  it('la clave de sesion lleva el prefijo del Supervisor', async () => {
    const ev = evento();
    await POST(ev);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.identificador_sesion).toBe('snoc:u-7');
  });
});

describe('POST — fallos', () => {
  it('sin usuario responde 401 y no llama a nadie', async () => {
    const ev = { ...evento(), locals: {} };
    const r = await POST(ev);
    expect(r.status).toBe(401);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('si el perfil falla no se le habla al motor', async () => {
    apiRequest.mockRejectedValueOnce(new Error('Organization context is required.'));
    const ev = evento();
    const r = await POST(ev);
    expect(r.status).toBe(502);
    expect(ev.fetch).not.toHaveBeenCalled();
  });

  it('un mensaje vacio se rechaza antes de gastar un turno', async () => {
    const ev = evento({ mensaje: '   ' });
    const r = await POST(ev);
    expect(r.status).toBe(400);
    expect(ev.fetch).not.toHaveBeenCalled();
  });

  it('si el contexto del Supervisor falla, la pregunta viaja igual', async () => {
    //  El chat no se cae porque una consulta de indicadores fallo.
    apiRequest
      .mockResolvedValueOnce({ user_obj: { id: 'p-9', name: 'Ana' } })  // /profile/
      .mockRejectedValueOnce(new Error('503'))                           // propuestas
      .mockRejectedValueOnce(new Error('503'));                          // indicadores
    const ev = evento();
    const r = await POST(ev);
    expect(r.status).toBe(200);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.mensaje).toBe('hola');
    expect(cuerpo.mensaje).not.toContain('Estado del Supervisor');
  });
});

describe('GET — el historial', () => {
  it('pide el hilo de ESTA sesion, con el prefijo', async () => {
    const ev = evento();
    ev.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ mensajes: [] }) }));
    await GET(ev);
    const url = String(ev.fetch.mock.calls[0][0]);
    expect(url).toContain('identificador_sesion=snoc%3Au-7');
    expect(url).toContain('tenant=rapilink');
  });

  it('sin usuario responde 401', async () => {
    const r = await GET({ ...evento(), locals: {} });
    expect(r.status).toBe(401);
  });
});
