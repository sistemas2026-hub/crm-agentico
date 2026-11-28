import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Buscar en los mensajes: la ruta del servidor y su puente al motor, JUNTOS
 * (11/11/2026). No se mockea el puente: lo que se prueba es la cadena
 * navegador → esta ruta → buscarEnMensajes → motor, y que en ninguno de los
 * saltos se pierda o se renombre un campo. El 29/09/2026 `requiere_noc`
 * viajaba bien del backend y la capa servidor lo dejaba caer; la bandeja del
 * NOC quedó vacía para siempre con todas las pruebas en verde.
 */
const { envMock } = vi.hoisted(() => ({ envMock: /** @type {Record<string, string>} */ ({}) }));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { GET } = await import('./+server.js');

/** Lo que devuelve el motor, tal cual (api.py::conversaciones_buscar). */
const DEL_MOTOR = {
  resultados: [
    {
      mensaje_id: 'm-1',
      conversation_id: 'c-1',
      rol: 'nota',
      es_nota: true,
      creado_en: '2026-11-11T13:00:00+00:00',
      fragmento: '…revisar el poste caído de la calle 8',
      nombre_cliente: 'Ana Pérez',
      usuario_externo: '573001',
      estado: 'cerrada',
      canal: 'whatsapp',
      canal_operativo: true
    }
  ],
  tope: 30
};

let fetchMock = vi.fn();
const evento = (/** @type {string} */ q, user = /** @type {any} */ ({ id: 'u1' }), vista = /** @type {string|null} */ (null)) =>
  /** @type {any} */ ({
    url: new URL(
      `http://crm/api/conversaciones/buscar?q=${encodeURIComponent(q)}` +
        (vista === null ? '' : `&vista=${encodeURIComponent(vista)}`)
    ),
    locals: { user, tenant: 'empresa-x' },
    fetch: fetchMock,
    request: new Request('http://crm/api/conversaciones/buscar')
  });

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
  envMock.PRIVATE_ASISTENTE_URL = 'http://motor:5000';
  fetchMock = vi.fn(async () => new Response(JSON.stringify(DEL_MOTOR), { status: 200 }));
});

describe('GET /api/conversaciones/buscar', () => {
  it('EL EFECTO: cada campo que la pantalla usa llega igual que lo mandó el motor', async () => {
    const r = await GET(evento('poste caído'));
    expect(r.status).toBe(200);
    const datos = await r.json();
    const [x] = datos.resultados;
    expect(x).toEqual({
      conversation_id: 'c-1',
      mensaje_id: 'm-1',
      rol: 'nota',
      es_nota: true,
      creado_en: '2026-11-11T13:00:00+00:00',
      fragmento: '…revisar el poste caído de la calle 8',
      nombre_cliente: 'Ana Pérez',
      usuario_externo: '573001',
      estado: 'cerrada',
      canal_operativo: true
    });
    expect(datos.tope).toBe(30);
  });

  it('le pregunta al motor con el tenant de la SESIÓN y la búsqueda codificada', async () => {
    await GET(evento('50% & co'));
    const url = new URL(String(/** @type {any} */ (fetchMock.mock.calls[0])[0]));
    expect(url.pathname).toBe('/conversaciones/buscar');
    expect(url.searchParams.get('tenant')).toBe('empresa-x');
    expect(url.searchParams.get('q')).toBe('50% & co');
  });

  it('EL EFECTO (auditoría H2): la vista de canales llega al motor, que filtra antes del tope', async () => {
    for (const vista of ['operativo', 'pruebas', 'todos']) {
      fetchMock.mockClear();
      const r = await GET(evento('poste caído', undefined, vista));
      expect(r.status).toBe(200);
      const url = new URL(String(/** @type {any} */ (fetchMock.mock.calls[0])[0]));
      expect(url.searchParams.get('vista')).toBe(vista);
    }
  });

  it('sin vista, «todos»; una vista desconocida: 400 y no se le pregunta al motor', async () => {
    await GET(evento('poste caído'));
    const url = new URL(String(/** @type {any} */ (fetchMock.mock.calls[0])[0]));
    expect(url.searchParams.get('vista')).toBe('todos');
    fetchMock.mockClear();
    expect((await GET(evento('poste caído', undefined, 'reales'))).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('los espacios se normalizan antes de medir y de mandar', async () => {
    await GET(evento('   poste    caído  '));
    const url = new URL(String(/** @type {any} */ (fetchMock.mock.calls[0])[0]));
    expect(url.searchParams.get('q')).toBe('poste caído');
  });

  it('menos de 3 o más de 100 letras: 400, y no se le pregunta al motor', async () => {
    expect((await GET(evento('ab'))).status).toBe(400);
    expect((await GET(evento('   ab   '))).status).toBe(400);
    expect((await GET(evento('x'.repeat(101)))).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sin sesión: 401', async () => {
    expect((await GET(evento('poste', /** @type {any} */ (null)))).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('el error del motor vuelve con su texto, sin la búsqueda', async () => {
    fetchMock = vi.fn(
      async () => new Response(JSON.stringify({ error: 'No se pudo buscar en los mensajes.' }), { status: 500 })
    );
    const r = await GET(evento('poste caído'));
    expect(r.status).toBe(502);
    const datos = await r.json();
    expect(datos.error).toBe('No se pudo buscar en los mensajes.');
  });

  it('sin asistente configurado no inventa resultados', async () => {
    delete envMock.PRIVATE_ASISTENTE_URL;
    const r = await GET(evento('poste caído'));
    expect(r.status).toBe(502);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
