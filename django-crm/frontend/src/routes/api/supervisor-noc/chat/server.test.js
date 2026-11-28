import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * EL PROXY DE LA BURBUJA DEL SUPERVISOR  --  despues de la reconciliacion
 * =======================================================================
 *
 * QUE CAMBIO, Y QUE NO
 * --------------------
 * La ruta dejo de hablarle al motor (`POST /chat`, el agente GENERICO del
 * tenant) y ahora le habla a Django (`/operaciones/supervisor/chat/`, el
 * Supervisor DEDICADO con sus 15 herramientas). Las pruebas que afirmaban
 * sobre el motor --el `profile_id` resuelto del lado del servidor, la clave de
 * sesion con prefijo, el bloque de contexto-- ya no describen esta ruta: lo que
 * resolvian vive ahora en `operaciones/chat.py` y en la tabla
 * `ConversacionSupervisor`, y se prueba alla
 * (`operaciones/tests/test_p5_chat_supervisor.py`,
 * `test_reconciliacion_historial.py`).
 *
 * Lo que NO cambio son las GARANTIAS, y por eso siguen aqui, reescritas contra
 * el contrato nuevo:
 *
 *   el JWT llega          lo que se le pasa a `apiRequest` tiene que servir
 *                         para sacar el token (ver abajo: es el defecto que se
 *                         pago en produccion).
 *   la identidad no       no se manda `profile_id` ni tenant desde aca; los
 *   viaja del navegador   saca Django de la credencial.
 *   sin sesion, nada      401 y ni una llamada.
 *   un vacio no gasta     se rechaza antes de pedir un turno.
 *   un turno
 *
 * EL DEFECTO QUE ESTO VIENE A FIJAR  --  medido el 05/10/2026 en produccion
 * -------------------------------------------------------------------------
 * La burbuja se desplego y la primera pregunta devolvio
 *
 *     "Organization context is required. Please login again."
 *
 * `apiRequest(endpoint, options, locals)` resuelve el token asi:
 *
 *     const cookies = locals.cookies || locals;
 *     const accessToken = cookies?.get?.('jwt_access');
 *
 * En un `+server.js` el evento trae `cookies` APARTE de `locals`, y
 * `hooks.server.js` nunca lo copia adentro. El fallback agarraba `locals`,
 * `.get` no existia, no salia `Authorization` y Django respondia 403. El
 * mensaje mandaba a revisar el login, que estaba bien.
 *
 * POR QUE SE AFIRMA SOBRE EL TOKEN Y NO SOBRE LA FORMA DE LA LLAMADA
 * -------------------------------------------------------------------
 * Una prueba que dijera "se llamo con { cookies }" pasaria igual si manana
 * `apiRequest` cambiara de donde saca el token. Lo que importa es el EFECTO:
 * que de lo que se le pasa se pueda extraer el JWT con la MISMA expresion que
 * usa `apiRequest`. Por eso el doble la reproduce textualmente.
 *
 * Y AHORA APLICA A LOS DOS VERBOS. Antes el GET iba al motor con
 * `headersMotor()` y no pasaba por `apiRequest`; ahora los dos van por Django,
 * asi que los dos pueden tener el defecto y los dos se prueban.
 */

const TOKEN = 'jwt-de-prueba';

/** Lo que `apiRequest` hace para sacar el token, copiado tal cual. */
function tokenQueVeria(tercerArgumento) {
  const cookies = tercerArgumento?.cookies || tercerArgumento;
  return cookies?.get?.('jwt_access');
}

const apiRequest = vi.fn();

vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
vi.mock('$lib/server/v2/supervisor-noc.js', () => ({
  traducirError: (err) => ({
    mensaje: err?.message || 'fallo',
    codigo: 'TRADUCIDO',
    status: err?.status ?? 502
  })
}));

const { POST, GET } = await import('./+server.js');

/** El `cookies` que SvelteKit entrega en un +server.js. */
const cookies = { get: (n) => (n === 'jwt_access' ? TOKEN : undefined) };

/**
 * Lo que `hooks.server.js` deja en locals: user, org, org_name, org_settings.
 *
 * NO lleva `profile`, y eso es el estado REAL -- no una simplificacion del
 * doble. Fue asi como se encontro que la version local de esta ruta
 * comprobaba `locals.profile?.role` y contestaba 403 a todo el mundo.
 */
const locals = {
  user: { id: 'u-7' },
  org: { id: 'org-1' },
  org_name: 'Rapilink',
  org_settings: {}
};

function evento(cuerpo = { mensaje: 'hola' }) {
  return {
    request: { json: async () => cuerpo },
    locals: structuredClone(locals),
    cookies
  };
}

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({
    conversacion_id: 'c-1',
    respuesta: 'listo',
    herramientas: ['listar_situaciones'],
    mensajes: []
  });
});

// ============================================================================
//  POST  --  la identidad llega autenticada
// ============================================================================

describe('POST — la identidad llega autenticada', () => {
  it('de lo que se le pasa a apiRequest SE PUEDE sacar el JWT', async () => {
    await POST(evento());

    expect(apiRequest).toHaveBeenCalledTimes(1);
    const tercero = apiRequest.mock.calls[0][2];
    expect(tokenQueVeria(tercero)).toBe(TOKEN);
  });

  it('lo que recibe tiene un .get llamable; locals no lo tiene', async () => {
    await POST(evento());

    const tercero = apiRequest.mock.calls[0][2];
    expect(typeof (tercero?.cookies || tercero)?.get).toBe('function');
    //  El contrapunto: si se hubiera pasado `locals`, esto seria undefined.
    expect(tokenQueVeria(locals)).toBeUndefined();
  });

  it('va a la ruta del Supervisor DEDICADO, no al /chat del motor', async () => {
    await POST(evento());

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/supervisor/chat/');
    const todas = JSON.stringify(apiRequest.mock.calls);
    expect(todas).not.toContain('/chat/historial');
    expect(todas).not.toContain('motor');
  });

  it('NO manda profile_id ni tenant: los saca Django de la credencial', async () => {
    await POST(evento({ mensaje: 'hola', profile_id: 'otro', tenant: 'ajeno' }));

    const body = apiRequest.mock.calls[0][1].body;
    expect(body).toEqual({ mensaje: 'hola' });
    expect(body.profile_id).toBeUndefined();
    expect(body.tenant).toBeUndefined();
  });

  it('reenvia solo los campos que la vista entiende', async () => {
    await POST(
      evento({
        mensaje: 'hola',
        conversacion_id: 'c-9',
        situacion: 'S-001',
        caso: 'k-2',
        inventado: 'no deberia viajar'
      })
    );

    expect(apiRequest.mock.calls[0][1].body).toEqual({
      mensaje: 'hola',
      conversacion_id: 'c-9',
      situacion: 'S-001',
      caso: 'k-2'
    });
  });

  it('devuelve la traza de herramientas que uso el Supervisor', async () => {
    const r = await POST(evento());
    const d = await r.json();

    expect(d.herramientas).toEqual(['listar_situaciones']);
    expect(d.conversacion_id).toBe('c-1');
    expect(d.respuesta).toBe('listo');
  });
});

// ============================================================================
//  POST  --  fallos
// ============================================================================

describe('POST — fallos', () => {
  it('sin usuario responde 401 y no llama a nadie', async () => {
    const e = evento();
    e.locals = {};

    const r = await POST(e);

    expect(r.status).toBe(401);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un mensaje vacio se rechaza antes de gastar un turno', async () => {
    const r = await POST(evento({ mensaje: '   ' }));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un mensaje demasiado largo se rechaza del lado del servidor', async () => {
    const r = await POST(evento({ mensaje: 'x'.repeat(4001) }));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un cuerpo que no es JSON responde 400, no revienta', async () => {
    const e = evento();
    e.request = {
      json: async () => {
        throw new Error('no es json');
      }
    };

    const r = await POST(e);

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un rol insuficiente lo decide DJANGO, y su 403 se propaga', async () => {
    //  La garantia del permiso vive en `EsJefeDeOperaciones`. Esta ruta no la
    //  duplica -- ver `quienPregunta` -- asi que lo que se afirma es que el 403
    //  de Django llega al navegador en vez de perderse en un 502.
    apiRequest.mockRejectedValue(
      Object.assign(new Error('Sin permiso'), { status: 403 })
    );

    const r = await POST(evento());

    expect(r.status).toBe(403);
    expect((await r.json()).error).toBe('Sin permiso');
  });

  it('el detalle tecnico no se filtra sin pasar por traducirError', async () => {
    apiRequest.mockRejectedValue(new Error('conectando a http://motor:5000'));

    const r = await POST(evento());
    const d = await r.json();

    expect(d.codigo).toBe('TRADUCIDO');
    expect(r.status).toBe(502);
  });
});

// ============================================================================
//  GET  --  el historial
// ============================================================================

describe('GET — el historial', () => {
  it('pide el hilo por Django, con el JWT extraible', async () => {
    await GET({ locals: structuredClone(locals), cookies });

    expect(apiRequest).toHaveBeenCalledTimes(1);
    expect(apiRequest.mock.calls[0][0]).toContain('/operaciones/supervisor/chat/');
    expect(tokenQueVeria(apiRequest.mock.calls[0][2])).toBe(TOKEN);
  });

  it('pide un limite, y el tope real lo pone el servidor', async () => {
    await GET({ locals: structuredClone(locals), cookies });

    expect(apiRequest.mock.calls[0][0]).toContain('limite=60');
  });

  it('devuelve los mensajes tal como vienen, sin reinterpretarlos', async () => {
    const mensajes = [
      { id: 'm1', rol: 'user', contenido: 'hola', creado_en: '2026-10-05T10:00:00Z' },
      { id: 'm2', rol: 'assistant', contenido: 'hola', creado_en: '2026-10-05T10:00:01Z' }
    ];
    apiRequest.mockResolvedValue({ conversacion_id: 'c-1', mensajes });

    const d = await (await GET({ locals: structuredClone(locals), cookies })).json();

    expect(d.mensajes).toEqual(mensajes);
    expect(d.conversacion_id).toBe('c-1');
  });

  it('si Django no devuelve una lista, se contesta una lista vacia', async () => {
    apiRequest.mockResolvedValue({ conversacion_id: null, mensajes: null });

    const d = await (await GET({ locals: structuredClone(locals), cookies })).json();

    expect(d.mensajes).toEqual([]);
  });

  it('sin usuario responde 401', async () => {
    const r = await GET({ locals: {}, cookies });

    expect(r.status).toBe(401);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});
