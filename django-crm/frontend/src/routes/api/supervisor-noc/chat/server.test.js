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
const locals = { user: { id: 'u-7' }, org: { id: 'org-1' }, tenant: 'rapilink',
                 profile: { role: 'ADMIN' } };

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

  it('resuelve el nombre del lado del servidor, no del cuerpo', async () => {
    //  Ya no se resuelve 'profile_id' -- la burbuja pide el rol por nombre.
    //  Lo que sigue saliendo del servidor es quien firma.
    const ev = evento({ mensaje: 'hola', nombre_colaborador: 'OTRO' });
    await POST(ev);
    expect(apiRequest.mock.calls.some((c) => c[0] === '/profile/')).toBe(true);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.nombre_colaborador).toBe('Ana');
  });

  it('le habla al rol supervisor_noc, no a los agentes del colaborador', async () => {
    //  Lo que desbloquea el "no tienes ningun agente asignado": pedir el rol
    //  por nombre no pasa por 'agentes_de_colaborador'.
    const ev = evento();
    await POST(ev);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.rol).toBe('supervisor_noc');
    expect(cuerpo.profile_id).toBeUndefined();
  });

  it('nada del cuerpo decide con que agente se habla', async () => {
    const ev = evento({ mensaje: 'hola', rol: 'administracion', profile_id: 'INTRUSO' });
    await POST(ev);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.rol).toBe('supervisor_noc');
    expect(cuerpo.profile_id).toBeUndefined();
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

  it('si no se puede leer el nombre, la pregunta sale igual', async () => {
    //  El nombre es una cortesia para firmar, no un control: quien decide el
    //  acceso es la puerta por perfil, que ya corrio. Cortar aca dejaria el
    //  chat caido por algo que no protege a nadie.
    apiRequest.mockRejectedValue(new Error('502'));
    const ev = evento();
    const r = await POST(ev);
    expect(r.status).toBe(200);
    const cuerpo = JSON.parse(ev.fetch.mock.calls.at(-1)[1].body);
    expect(cuerpo.nombre_colaborador).toBe('');
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

describe('la puerta por perfil — quien puede supervisar', () => {
  //  Pedir el rol por nombre saltea 'agentes_de_colaborador', que era el
  //  control que decidia quien accede. Si esta puerta no estuviera, cualquier
  //  usuario autenticado de la empresa tendria el estado de la operacion.
  for (const role of ['ADMIN', 'SUPERVISOR', 'OPERACIONES']) {
    it(`${role} entra`, async () => {
      const ev = evento();
      ev.locals.profile = { role };
      expect((await POST(ev)).status).toBe(200);
    });
  }

  for (const role of ['USER', 'user', 'admin', '', undefined]) {
    it(`${JSON.stringify(role)} NO entra`, async () => {
      const ev = evento();
      ev.locals.profile = { role };
      const r = await POST(ev);
      expect(r.status).toBe(403);
      expect(ev.fetch).not.toHaveBeenCalled();
    });
  }

  it('sin perfil tampoco: fail-closed', async () => {
    const ev = evento();
    delete ev.locals.profile;
    expect((await POST(ev)).status).toBe(403);
  });

  it('la puerta vale tambien para leer el historial', async () => {
    const ev = evento();
    ev.locals.profile = { role: 'USER' };
    expect((await GET(ev)).status).toBe(403);
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
