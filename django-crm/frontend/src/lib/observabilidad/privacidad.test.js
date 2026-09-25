/**
 * NINGUN DATO DEL CLIENTE SALE POR NINGUN GANCHO DE OBSERVABILIDAD.
 *
 * Se inyectan valores canario --nombre, telefono, cedula, correo, BSUID,
 * wamid, JWT, texto de conversacion-- en cada lugar por donde Sentry podria
 * sacarlos (evento, migas, transaccion, log, contexto, extra, request,
 * frames) y se exige que ninguno aparezca en lo que sale. Ademas se exige que
 * lo util SI quede: tipo de error, archivo, funcion, linea, ruta sin query.
 *
 * Criterio (OBSERVABILIDAD_Y_PRIVACIDAD.md): responder "que fallo" sin poder
 * responder "quien era el cliente".
 */
import { describe, expect, it } from 'vitest';
import {
  CLAVES_PROHIBIDAS,
  ERRORES_IGNORADOS,
  OPCIONES_REPLAY,
  SELECTORES_PRIVADOS,
  describirError,
  limpiarEvento,
  limpiarLog,
  limpiarMiga,
  limpiarObjeto,
  limpiarTransaccion,
  mensajeSeguro,
  pareceNombre,
  redactarRuta,
  redactarTexto,
  sinQuery
} from './privacidad.js';

const CANARIOS = {
  nombre: 'Juan Pérez',
  telefono: '3001234567',
  telefonoIntl: '+57 300 123 4567',
  cedula: '123456789',
  correo: 'juan.perez@example.com',
  bsuid: 'CO.1360399936298471',
  wamid: 'wamid.HBgLNTczMDAxMjM0NTY3FQIAERgSN0Q5',
  jwt: 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dGVzdF9maXJtYV9mYWxzYQ',
  mensaje: 'mi cédula es 123456789 y me llamo Juan Pérez'
};

/** Todo lo que no puede aparecer en una salida serializada. */
const PROHIBIDO = ['Juan', 'Pérez', 'Perez', '3001234567', '300 123 4567', '123456789',
  'juan.perez', 'example.com', '1360399936298471', 'HBgLNTczMDAxMjM0NTY3', 'eyJhbGciOiJIUzI1NiJ9'];

function sinCanarios(valor) {
  const texto = JSON.stringify(valor) ?? '';
  const filtrados = PROHIBIDO.filter((p) => texto.includes(p));
  return { limpio: filtrados.length === 0, filtrados };
}

describe('redactarTexto (capa 1: patrones)', () => {
  it('reemplaza correos, BSUID, wamid, JWT, telefonos y cadenas de digitos', () => {
    const texto = `${CANARIOS.correo} ${CANARIOS.bsuid} ${CANARIOS.wamid} ${CANARIOS.jwt} ` +
      `${CANARIOS.telefono} ${CANARIOS.telefonoIntl} cedula ${CANARIOS.cedula}`;
    const salida = redactarTexto(texto);
    expect(sinCanarios(salida)).toEqual({ limpio: true, filtrados: [] });
    expect(salida).toContain('<correo>');
    expect(salida).toContain('<bsuid>');
    expect(salida).toContain('<wamid>');
    expect(salida).toContain('<jwt>');
    expect(salida).toContain('<telefono>');
    expect(salida).toContain('<numero>');
  });
  it('deja pasar texto de operacion sin datos', () => {
    expect(redactarTexto('HTTP 502: Bad Gateway en /conversaciones')).toBe('HTTP 502: Bad Gateway en /conversaciones');
  });
  it('acota el largo', () => {
    expect(redactarTexto('x'.repeat(5000)).length).toBeLessThan(600);
  });
});

describe('mensajeSeguro (capa 2: vocabulario)', () => {
  it('el ejemplo del brief: no sale "Error cargando cliente Juan Pérez con cédula 123456"', () => {
    const salida = mensajeSeguro('Error cargando cliente Juan Pérez con cédula 123456');
    expect(sinCanarios(salida).limpio).toBe(true);
    expect(salida).toMatch(/^mensaje omitido \(posible dato personal\) #[0-9a-f]{6}$/);
  });
  it('un nombre sin digitos tambien se va, porque el mensaje habla de una persona', () => {
    expect(mensajeSeguro('no se encontro al titular Juan Pérez')).not.toContain('Juan');
  });
  it('un nombre sin ninguna palabra del vocabulario tambien se va: tiene forma de nombre', () => {
    expect(mensajeSeguro('Failed to load Juan Pérez')).not.toContain('Juan');
    expect(mensajeSeguro('atendido Juan Pérez')).not.toContain('Pérez');
    expect(mensajeSeguro('no aparece MARIO SABANAGRANDE')).not.toContain('MARIO');
    expect(pareceNombre('Ana Cruz')).toBe(true);
  });
  it('las frases de estado HTTP y las siglas no se confunden con nombres', () => {
    for (const m of ['HTTP 404: Not Found', 'HTTP 502: Bad Gateway', 'Internal Server Error',
      'API request failed: GET /x', 'Failed to fetch', 'Too Many Requests', 'JSON Parse Error']) {
      expect(mensajeSeguro(m), m).toBe(m);
    }
    expect(pareceNombre('Not Found')).toBe(false);
  });
  it('un mensaje de operacion queda legible', () => {
    expect(mensajeSeguro('Error cargando conversación')).toBe('Error cargando conversación');
    expect(mensajeSeguro('HTTP 404: Not Found')).toBe('HTTP 404: Not Found');
  });
  it('el marcador es estable para el mismo texto (sirve para agrupar) y distinto para otro', () => {
    const a = mensajeSeguro(`cliente ${CANARIOS.nombre}`);
    expect(mensajeSeguro(`cliente ${CANARIOS.nombre}`)).toBe(a);
    expect(mensajeSeguro('cliente Otra Persona')).not.toBe(a);
  });
});

describe('sinQuery', () => {
  it('conserva la ruta y tira query y fragmento', () => {
    expect(sinQuery('/conversaciones?buscar=3001234567&t=eyJ')).toBe('/conversaciones');
    expect(sinQuery('https://agent.example/api/x#frag')).toBe('https://agent.example/api/x');
    expect(sinQuery(undefined)).toBeUndefined();
  });
});

describe('redactarRuta', () => {
  it('sin query, con los ids numericos reemplazados y los UUID intactos', () => {
    expect(redactarRuta('/api/clientes/5832/?x=1')).toBe('/api/clientes/<id>/');
    expect(redactarRuta('/api/clientes/5832')).toBe('/api/clientes/<id>');
    expect(redactarRuta('/conversaciones/dec658e9-af55-430d-97e3-eab1e8473e6c/mensajes'))
      .toBe('/conversaciones/dec658e9-af55-430d-97e3-eab1e8473e6c/mensajes');
    expect(redactarRuta('GET /api/clientes?telefono=3001234567')).toBe('GET /api/clientes');
    expect(redactarRuta('/_app/immutable/nodes/61.js?v=1')).toBe('/_app/immutable/nodes/61.js');
  });
  it('una ruta no se confunde con un mensaje que habla de clientes', () => {
    expect(limpiarObjeto({ endpoint: '/api/clientes/5832/' })).toEqual({ endpoint: '/api/clientes/<id>/' });
    expect(limpiarObjeto({ url: 'https://agent.example/conversaciones?q=x' }))
      .toEqual({ url: 'https://agent.example/conversaciones' });
  });
});

describe('limpiarObjeto (payload libre)', () => {
  it('elimina claves prohibidas y redacta texto en cualquier nivel', () => {
    const salida = limpiarObjeto({
      tipo: 'conversation_load_error',
      conversation_id: 'dec658e9-af55-430d-97e3-eab1e8473e6c',
      nombre_cliente: CANARIOS.nombre,
      telefono: CANARIOS.telefono,
      anidado: { cedula: CANARIOS.cedula, nota: `ver ${CANARIOS.correo}`, ok: 1 },
      lista: [{ mensaje: CANARIOS.mensaje }, `tel ${CANARIOS.telefono}`]
    });
    expect(sinCanarios(salida)).toEqual({ limpio: true, filtrados: [] });
    expect(salida.tipo).toBe('conversation_load_error');
    expect(salida.conversation_id).toBe('dec658e9-af55-430d-97e3-eab1e8473e6c');
    expect(salida.anidado.ok).toBe(1);
  });
  it('la lista de claves cubre lo que la bandeja pinta y lo que la sesion guarda', () => {
    for (const k of ['nombre_cliente', 'usuario_externo', 'autor_nombre', 'telefono', 'cedula',
      'texto', 'mensajes', 'respuesta', 'cookies', 'authorization', 'jwt_access', 'user']) {
      expect(CLAVES_PROHIBIDAS.has(k)).toBe(true);
    }
  });
  it('un texto libre dentro del payload pasa por las dos capas: un nombre sin digitos no sale', () => {
    const salida = limpiarObjeto({ detalle: `atendido ${CANARIOS.nombre}`, nota: 'todo bien' });
    expect(sinCanarios(salida).limpio).toBe(true);
    expect(salida.nota).toBe('todo bien');
  });
  it('los contextos de navegador y sistema no se confunden con nombres', () => {
    expect(limpiarObjeto({ name: 'Mobile Safari', version: '17.4' })).toEqual({ name: 'Mobile Safari', version: '17.4' });
    expect(limpiarObjeto({ name: 'Windows', version: '11' })).toEqual({ name: 'Windows', version: '11' });
    expect(limpiarObjeto({ name: 'Mac OS X' })).toEqual({ name: 'Mac OS X' });
  });
  it('no se cuelga con ciclos ni profundidad', () => {
    const a = { b: {} };
    a.b.c = a;
    expect(() => limpiarObjeto(a)).not.toThrow();
  });
});

describe('limpiarMiga (beforeBreadcrumb)', () => {
  it('console.error con el objeto de una conversacion: no sale nada del cliente', () => {
    const miga = limpiarMiga({
      category: 'console', level: 'error',
      message: `Failed to load ${CANARIOS.nombre}`,
      data: { arguments: ['Failed', { nombre_cliente: CANARIOS.nombre, usuario_externo: CANARIOS.bsuid,
        mensajes: [{ texto: CANARIOS.mensaje }], id: 'conv-1' }], logger: 'console' }
    });
    expect(sinCanarios(miga)).toEqual({ limpio: true, filtrados: [] });
    expect(miga.data.arguments[1].id).toBe('conv-1');
  });
  it('fetch/xhr: ruta sin query, sin cuerpos', () => {
    const miga = limpiarMiga({
      category: 'fetch',
      data: { method: 'GET', url: `/api/conversaciones?buscar=${CANARIOS.telefono}`,
        status_code: 500, request_body: CANARIOS.mensaje, response_body: CANARIOS.nombre }
    });
    expect(sinCanarios(miga).limpio).toBe(true);
    expect(miga.data.url).toBe('/api/conversaciones');
    expect(miga.data.status_code).toBe(500);
    expect(miga.data.request_body).toBeUndefined();
  });
  it('navegacion: from/to sin query', () => {
    const miga = limpiarMiga({ category: 'navigation', data: { from: `/x?q=${CANARIOS.cedula}`, to: '/y?t=1' } });
    expect(miga.data).toEqual({ from: '/x', to: '/y' });
  });
});

describe('limpiarEvento (beforeSend)', () => {
  const evento = {
    message: `Error cargando cliente ${CANARIOS.nombre} con cédula ${CANARIOS.cedula}`,
    user: { id: '7', ip_address: '190.1.2.3', email: CANARIOS.correo },
    server_name: 'srv-1',
    request: { url: `/conversaciones/abc?tel=${CANARIOS.telefono}`, method: 'GET',
      headers: { Cookie: `jwt_access=${CANARIOS.jwt}` }, cookies: { jwt_access: CANARIOS.jwt },
      data: CANARIOS.mensaje, query_string: `tel=${CANARIOS.telefono}` },
    exception: { values: [{ type: 'TypeError',
      value: `no se pudo leer el nombre del titular ${CANARIOS.nombre}`,
      stacktrace: { frames: [{ filename: '/_app/immutable/nodes/61.js?v=1', function: 'cargar',
        lineno: 12, colno: 5, in_app: true, vars: { nombre: CANARIOS.nombre },
        context_line: `const n = "${CANARIOS.nombre}"` }] },
      mechanism: { type: 'onerror', handled: false, data: { nombre: CANARIOS.nombre } } }] },
    breadcrumbs: [{ category: 'console', message: CANARIOS.mensaje, data: { arguments: [CANARIOS.mensaje] } }],
    extra: { conversacion: { nombre_cliente: CANARIOS.nombre }, intento: 2, nota: `wamid ${CANARIOS.wamid}` },
    tags: { tenant: 'rapilink', telefono: CANARIOS.telefono },
    contexts: { user: { name: CANARIOS.nombre }, geo: { city: 'Cali' },
      browser: { name: 'Chrome', version: '128' }, dexter: { texto: CANARIOS.mensaje, rol: 'soporte' } },
    transaction: `/conversaciones/[id]?tel=${CANARIOS.telefono}`
  };

  it('no sale ni un canario, por ninguna via', () => {
    const salida = limpiarEvento(evento);
    expect(sinCanarios(salida)).toEqual({ limpio: true, filtrados: [] });
  });
  it('y lo que sirve para saber que fallo sigue ahi', () => {
    const salida = limpiarEvento(evento);
    expect(salida.exception.values[0].type).toBe('TypeError');
    const frame = salida.exception.values[0].stacktrace.frames[0];
    expect(frame).toEqual({ filename: '/_app/immutable/nodes/61.js', function: 'cargar', lineno: 12, colno: 5, in_app: true });
    expect(salida.request).toEqual({ url: '/conversaciones/abc', method: 'GET' });
    expect(salida.transaction).toBe('/conversaciones/[id]');
    expect(salida.tags.tenant).toBe('rapilink');
    expect(salida.extra.intento).toBe(2);
    expect(salida.contexts.browser).toEqual({ name: 'Chrome', version: '128' });
    expect(salida.contexts.dexter.rol).toBe('soporte');
    expect(salida.user).toBeUndefined();
    expect(salida.server_name).toBeUndefined();
  });
  it('falla cerrado: si el evento no se puede limpiar, no sale', () => {
    expect(limpiarEvento(null)).toBeNull();
    expect(limpiarEvento('x')).toBeNull();
  });
});

describe('limpiarTransaccion (beforeSendTransaction)', () => {
  it('spans: descripciones y urls sin query, data sin claves prohibidas', () => {
    const salida = limpiarTransaccion({
      transaction: 'GET /api/conversaciones/[id]/mensajes',
      request: { url: `/api/x?buscar=${CANARIOS.nombre}`, cookies: { a: CANARIOS.jwt } },
      spans: [{ description: `GET /api/clientes?telefono=${CANARIOS.telefono}`,
        data: { 'http.url': `/api/clientes?telefono=${CANARIOS.telefono}`, respuesta: CANARIOS.nombre, 'http.status_code': 200 } }]
    });
    expect(sinCanarios(salida)).toEqual({ limpio: true, filtrados: [] });
    expect(salida.spans[0].description).toBe('GET /api/clientes');
    expect(salida.spans[0].data['http.url']).toBe('/api/clientes');
    expect(salida.spans[0].data['http.status_code']).toBe(200);
  });
});

describe('limpiarLog (beforeSendLog)', () => {
  it('mensaje y atributos limpios', () => {
    const salida = limpiarLog({ level: 'info', message: `atendido ${CANARIOS.nombre}`,
      attributes: { conversation_id: 'c1', telefono: CANARIOS.telefono, detalle: CANARIOS.mensaje } });
    expect(sinCanarios(salida)).toEqual({ limpio: true, filtrados: [] });
    expect(salida.attributes.conversation_id).toBe('c1');
  });
});

describe('describirError (para console.* en el cliente)', () => {
  it('reduce un error de fetch a tipo, mensaje seguro, status y codigo', () => {
    const err = Object.assign(new Error(`Cliente ${CANARIOS.nombre} no encontrado`), {
      status: 404, code: 'ENOTFOUND',
      response: { data: { detail: CANARIOS.mensaje }, headers: { Authorization: `Bearer ${CANARIOS.jwt}` } },
      config: { data: CANARIOS.mensaje, headers: { Authorization: `Bearer ${CANARIOS.jwt}` } }
    });
    const salida = describirError(err);
    expect(sinCanarios(salida)).toEqual({ limpio: true, filtrados: [] });
    expect(salida).toEqual(expect.objectContaining({ tipo: 'Error', status: 404, codigo: 'ENOTFOUND' }));
    expect(Object.keys(salida).sort()).toEqual(['codigo', 'mensaje', 'status', 'tipo']);
  });
  it('no rompe con valores raros', () => {
    expect(describirError(null)).toEqual({ tipo: 'desconocido' });
    expect(describirError('texto')).toEqual({ tipo: 'string', mensaje: 'texto' });
  });
});

describe('replay y ruido', () => {
  it('el replay enmascara todo, bloquea las areas con datos y no captura cuerpos de red', () => {
    expect(OPCIONES_REPLAY.maskAllText).toBe(true);
    expect(OPCIONES_REPLAY.maskAllInputs).toBe(true);
    expect(OPCIONES_REPLAY.blockAllMedia).toBe(true);
    expect(OPCIONES_REPLAY.networkDetailAllowUrls).toEqual([]);
    expect(OPCIONES_REPLAY.block).toBe(SELECTORES_PRIVADOS);
    expect(SELECTORES_PRIVADOS).toContain('[data-privado]');
    expect(SELECTORES_PRIVADOS).toContain('.mesa.bandeja');
  });
  it('las extensiones del navegador se ignoran', () => {
    expect(ERRORES_IGNORADOS.some((r) => r.test('Uncaught Error: Extension context invalidated.'))).toBe(true);
    expect(ERRORES_IGNORADOS.some((r) => r.test('A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received'))).toBe(true);
  });
});
