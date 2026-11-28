import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * «HECHO · DESHACER»: LO QUE LLEGA AL BACKEND Y LO QUE VUELVE (12/11/2026)
 * ======================================================================
 *
 * Se sustituye SOLO `apiRequest`, el borde con Django: la ruta, la capa
 * servidor (`deshacerHecho`) y el mensaje de error corren tal cual. Se afirma
 * sobre el efecto: la URL y el cuerpo que recibe el backend, y que un 409 con
 * su porqué llegue a la pantalla con ese porqué (no con el código).
 */

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({
  apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a)
}));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { POST } = await import('./[id]/deshacer/+server.js');

/** @param {any} cuerpo @param {string} [id] */
function pedido(cuerpo, id = 'a1b2') {
  return /** @type {any} */ ({
    params: { id },
    cookies: {},
    request: new Request('http://x/supervisor-noc/actividad/a1b2/deshacer', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: typeof cuerpo === 'string' ? cuerpo : JSON.stringify(cuerpo)
    })
  });
}

//  CON LLAVES, no `() => apiRequest.mockReset()`: vitest toma la función que
//  devuelve un `beforeEach` como limpieza y la llama al terminar la prueba
//  --o sea, llamaba al mock--, y el 409 de la última prueba reventaba ahí.
beforeEach(() => {
  apiRequest.mockReset();
});

describe('deshacer un hecho del Supervisor', () => {
  it('manda el motivo a la ruta del hecho y devuelve ok', async () => {
    apiRequest.mockResolvedValue({ deshecho: true, tipo: 'pase_a_despacho' });

    const r = await POST(pedido({ motivo: '  lo llamo yo  ' }));

    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true, deshecho: true, tipo: 'pase_a_despacho' });
    const [url, opciones] = apiRequest.mock.calls[0];
    expect(url).toBe('/operaciones/actividad-supervisor/a1b2/deshacer/');
    expect(opciones).toEqual({ method: 'POST', body: { motivo: 'lo llamo yo' } });
  });

  it('sin motivo no viaja nada', async () => {
    const r = await POST(pedido({ motivo: '   ' }));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un cuerpo ilegible es 400, no 500', async () => {
    const r = await POST(pedido('{no es json'));

    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('el 409 del backend llega con su porqué, no con el código', async () => {
    const e = Object.assign(new Error('YA_TIENE_ORDEN'), {
      status: 409,
      body: { error: 'YA_TIENE_ORDEN', detail: 'El caso ya tiene orden de trabajo: se cancela en Despacho.' }
    });
    apiRequest.mockImplementation(async () => {
      throw e;
    });

    const r = await POST(pedido({ motivo: 'x' }));

    expect(r.status).toBe(409);
    expect((await r.json()).error).toBe(
      'El caso ya tiene orden de trabajo: se cancela en Despacho.'
    );
  });
});
