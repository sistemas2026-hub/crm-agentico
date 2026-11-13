import { describe, it, expect, vi } from 'vitest';

/**
 * La traza del simulador y «reproducir» (12/11/2026): los dos intermediarios
 * nuevos y la espera de la traza que usa la pantalla. Es la cadena
 * motor -> capa servidor -> página, en el tramo que el motor no ve.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));

const { GET: traza } = await import('./+server.js');
const { GET: reproduccion } = await import('../reproduccion/+server.js');
const { esperarTraza } = await import('$lib/components/manual/traza.js');

const CONV = '0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0';
const TURNO = '1b1c2d3e-4f50-6172-8394-a5b6c7d8e9f1';

function evento(ruta, query, { rol = 'USER', cuerpo = {}, status = 200 } = {}) {
  const fetch = vi.fn(async (/** @type {any} */ _url, /** @type {any} */ _init) => new Response(JSON.stringify(cuerpo), { status }));
  return {
    fetch,
    ev: /** @type {any} */ ({
      url: new URL(`http://crm${ruta}${query}`),
      locals: { user: { id: 'u' }, profile: { role: rol } },
      fetch
    })
  };
}

describe('GET /api/simulador-whatsapp/traza', () => {
  it('pide la traza de ESE turno y la página recibe herramientas, área y errores', async () => {
    const { fetch, ev } = evento('/api/simulador-whatsapp/traza', `?conversacion=${CONV}&desde=${TURNO}`, {
      cuerpo: {
        completa: true, derivo_a: 'facturacion',
        herramientas: [{ herramienta: 'derivar', exito: true }],
        errores: [{ herramienta: 'x', codigo_error: 'TIMEOUT' }]
      }
    });
    const r = await traza(ev);
    const llamada = new URL(fetch.mock.calls[0][0]);
    expect(llamada.pathname).toBe('/simulador/traza');
    expect(llamada.searchParams.get('tenant')).toBe('empresa');
    expect(llamada.searchParams.get('conversacion_id')).toBe(CONV);
    expect(llamada.searchParams.get('desde_mensaje')).toBe(TURNO);
    const cuerpo = await r.json();
    expect(cuerpo).toMatchObject({ completa: true, derivo_a: 'facturacion' });
    expect(cuerpo.errores[0].codigo_error).toBe('TIMEOUT');
  });

  it('sin turno no pregunta', async () => {
    const { fetch, ev } = evento('/api/simulador-whatsapp/traza', `?conversacion=${CONV}`);
    expect((await traza(ev)).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('sin sesión no pregunta', async () => {
    const { fetch, ev } = evento('/api/simulador-whatsapp/traza', `?conversacion=${CONV}&desde=${TURNO}`);
    ev.locals.user = null;
    expect((await traza(ev)).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('GET /api/simulador-whatsapp/reproduccion', () => {
  it('un administrador recibe los mensajes del cliente', async () => {
    const { fetch, ev } = evento('/api/simulador-whatsapp/reproduccion', `?conversacion=${CONV}`,
      { rol: 'ADMIN', cuerpo: { mensajes: ['hola', 'sigue sin andar'] } });
    const r = await reproduccion(ev);
    expect(new URL(fetch.mock.calls[0][0]).searchParams.get('conversacion_id')).toBe(CONV);
    expect((await r.json()).mensajes).toEqual(['hola', 'sigue sin andar']);
  });

  it('quien no es administrador no los ve', async () => {
    const { fetch, ev } = evento('/api/simulador-whatsapp/reproduccion', `?conversacion=${CONV}`);
    expect((await reproduccion(ev)).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('una conversación inválida no llega al motor', async () => {
    const { fetch, ev } = evento('/api/simulador-whatsapp/reproduccion', '?conversacion=abc', { rol: 'ADMIN' });
    expect((await reproduccion(ev)).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('esperarTraza', () => {
  const sinEspera = { dormir: async () => {} };
  const respuesta = (/** @type {any} */ c, status = 200) =>
    new Response(JSON.stringify(c), { status });

  it('vuelve a preguntar mientras la traza no esté completa', async () => {
    const pedir = vi.fn()
      .mockResolvedValueOnce(respuesta({ completa: false, herramientas: [] }))
      .mockResolvedValueOnce(respuesta({ completa: true, herramientas: [{ herramienta: 'a' }] }));
    const t = await esperarTraza(pedir, CONV, TURNO, sinEspera);
    expect(pedir).toHaveBeenCalledTimes(2);
    expect(t.completa).toBe(true);
    expect(t.herramientas).toHaveLength(1);
  });

  it('pasado el tope devuelve lo que hay, marcado como incompleto', async () => {
    const pedir = vi.fn(async () => respuesta({ completa: false, herramientas: [{ herramienta: 'a' }] }));
    const t = await esperarTraza(pedir, CONV, TURNO, { ...sinEspera, intentos: 3 });
    expect(pedir).toHaveBeenCalledTimes(3);
    expect(t.completa).toBe(false);
    expect(t.herramientas).toHaveLength(1);
  });

  it('un rechazo no se reintenta: se dice', async () => {
    const pedir = vi.fn(async () => respuesta({ error: 'no' }, 403));
    const t = await esperarTraza(pedir, CONV, TURNO, sinEspera);
    expect(pedir).toHaveBeenCalledTimes(1);
    expect(t.error).toBe('no');
  });

  it('pregunta por el turno a su intermediario', async () => {
    const pedir = vi.fn(async (/** @type {string} */ _url) => respuesta({ completa: true }));
    await esperarTraza(pedir, CONV, TURNO, sinEspera);
    expect(pedir.mock.calls[0][0]).toBe(
      `/api/simulador-whatsapp/traza?conversacion=${CONV}&desde=${TURNO}`);
  });
});

describe('la pantalla del simulador dibuja la traza, leído del código', () => {
  it('pide la traza de cada turno con el mensaje del cliente que lo abrió', async () => {
    const { readFileSync } = await import('node:fs');
    const { fileURLToPath } = await import('node:url');
    const pagina = readFileSync(
      fileURLToPath(new URL('../../../(app)/simulador-whatsapp/+page.svelte', import.meta.url)), 'utf-8');
    expect(pagina).toMatch(/cargarTraza\(datos\.mensaje_id, datos\.conversacion_id, datos\.mensaje_usuario_id\)/);
    expect(pagina).toMatch(/<TrazaDelTurno traza=\{trazas\[m\.mensajeId\]\}/);
    expect(pagina).toMatch(/searchParams\.get\('reproducir'\)/);
    // El identificador de la reproducción no es un teléfono.
    expect(pagina).toMatch(/telefono = `reproduccion-/);
  });
});
