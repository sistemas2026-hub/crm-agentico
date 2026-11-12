import { describe, it, expect, vi, beforeEach } from 'vitest';

/*
 * La ruta del bloque «Campo» del ticket (12/11/2026): de la respuesta del
 * backend a lo que recibe el componente, sin capas que dejen caer un campo.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { GET } = await import('./+server.js');
const { tonoDeEstado, rotuloDeOrden, diaLegible, quienVa } = await import('$lib/v2/hilo-del-cliente.js');

const CASO = '11111111-2222-3333-4444-555555555555';
const FILA = {
  id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', numero: 188, tipo: 'Correctivo',
  estado_operativo: 'bloqueada', estado_etiqueta: 'Bloqueada', tecnico: 'Carlos Gómez',
  integrantes: 2, cuadrilla: 'Cuadrilla Norte', fecha: '2026-11-12', puede_abrir: true
};

/** @param {any} locals */
const evento = (locals) => /** @type {any} */ ({ params: { id: CASO }, cookies: {}, locals });

beforeEach(() => apiRequest.mockReset());

describe('GET /tickets/[id]/campo', () => {
  it('sin sesión, 401 y no se llama al backend', async () => {
    const r = await GET(evento({}));
    expect(r.status).toBe(401);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('entrega las visitas con todo lo que el bloque dibuja', async () => {
    apiRequest.mockResolvedValue({ caso_id: CASO, servicio: '4986', ordenes: [FILA] });
    const r = await GET(evento({ user: { id: 1 } }));
    expect(r.status).toBe(200);
    const d = await r.json();
    expect(d.servicio).toBe('4986');
    expect(d.ordenes[0]).toEqual(FILA);
  });

  it('el 403 del backend llega como 403 con un mensaje para personas', async () => {
    apiRequest.mockImplementationOnce(() => Promise.reject(Object.assign(new Error('x'), { status: 403 })));
    const r = await GET(evento({ user: { id: 1 } }));
    expect(r.status).toBe(403);
    expect((await r.json()).error).toMatch(/puede ver/);
  });
});

describe('cómo se lee una orden', () => {
  it('rótulo, tono, día y quién va', () => {
    expect(rotuloDeOrden(188)).toBe('OT-188');
    expect(tonoDeEstado('bloqueada')).toBe('rust');
    expect(tonoDeEstado('algo-nuevo')).toBe('slate');
    // Sin pasar por Date: en Bogotá, medianoche UTC sería el día anterior.
    expect(diaLegible('2026-11-12')).toBe('12 nov 2026');
    expect(quienVa(FILA)).toBe('Carlos Gómez y 1 más · Cuadrilla Norte');
    expect(quienVa({ tecnico: null })).toBe('Sin técnico asignado');
  });
});
