/**
 * La cadena de Plantillas: formulario → acción → API, y la vuelta.
 *
 * CLAUDE.md §6: el 29/09/2026 un dato viajaba bien desde el backend, con su
 * prueba en verde, y la capa servidor del frontend lo dejaba caer. Acá se
 * afirma lo que cada acción MANDA y lo que devuelve a la pantalla.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));

const modulo = await import('./+page.server.js');
/** Las acciones devuelven datos o `fail`; el tipo generado dice `void | ...`. */
const actions = /** @type {any} */ (modulo.actions);
const load = /** @type {any} */ (modulo.load);

const cookies = { get: () => 'token' };

/** @param {Record<string, string>} campos */
const peticion = (campos) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({ request: { formData: async () => f }, cookies });
};

/** Un error con la forma que arroja `apiRequest`. */
const httpError = (/** @type {number} */ status, /** @type {any} */ body) =>
  Object.assign(new Error(body?.error ?? 'x'), { status, body });

//  CON LLAVES, a propósito. `mockReset()` devuelve el mock, y vitest 4 toma una
//  función devuelta por `beforeEach` como LIMPIEZA y la llama al terminar la
//  prueba: una llamada más a la API simulada, que en los casos de error lanza
//  y pone en rojo una prueba cuyas afirmaciones pasaron todas. Costó cinco
//  hipótesis falsas encontrarlo (13/10/2026).
beforeEach(() => {
  apiRequest.mockReset();
});

/** Que la API falle, como falla `apiRequest`. @param {any} e */
const rechazar = (e) => apiRequest.mockRejectedValue(e);

describe('publicar', () => {
  it('manda la definición tal como la armó el editor, con nombre y labor', async () => {
    apiRequest.mockResolvedValue({ cambio: true, version: 3, ordenes_vivas: 0 });
    const definicion = { campos: [{ titulo: 'Qué se hizo', tipo: 'texto' }], evidencias: [] };

    await actions.publicar(peticion({
      id: 'abc', definicion: JSON.stringify(definicion), nombre: ' Retiro ', labor: 'trabajos'
    }));

    expect(apiRequest).toHaveBeenCalledWith(
      '/campo/plantillas/abc/publicar/',
      { method: 'POST', body: { definicion, nombre: 'Retiro', labor: 'trabajos' } },
      { cookies }
    );
  });

  it('sin nombre ni labor en el formulario, no los manda vacíos', async () => {
    //  Vacíos borrarían la labor, y la plantilla dejaría de repartirse.
    apiRequest.mockResolvedValue({ cambio: true, version: 2, ordenes_vivas: 0 });
    await actions.publicar(peticion({ id: 'abc', definicion: '{"campos":[]}' }));
    expect(apiRequest.mock.calls[0][1].body).toEqual({ definicion: { campos: [] } });
  });

  it('dice que las órdenes abiertas NO cambian', async () => {
    apiRequest.mockResolvedValue({ cambio: true, version: 2, ordenes_vivas: 4 });
    const r = await actions.publicar(peticion({ id: 'abc', definicion: '{"campos":[]}' }));
    expect(r.hecho).toContain('versión 2');
    expect(r.hecho).toContain('4 órdenes abiertas siguen con la versión anterior');
  });

  it('sin cambios lo dice, en vez de anunciar una versión que no existe', async () => {
    apiRequest.mockResolvedValue({ cambio: false, version: 1 });
    const r = await actions.publicar(peticion({ id: 'abc', definicion: '{"campos":[]}' }));
    expect(r.hecho).toMatch(/No había cambios/);
  });

  it('el error llega como FRASE, no como el código', async () => {
    //  apiRequest pone el código en `message`; la frase vive en body.detalle.
    rechazar(httpError(400, {
      error: 'FALTAN_OPCIONES', detalle: '«Resultado» necesita al menos dos opciones.'
    }));
    const r = await actions.publicar(peticion({ id: 'abc', definicion: '{"campos":[]}' }));
    expect(r.status).toBe(400);
    expect(r.data.error).toBe('«Resultado» necesita al menos dos opciones.');
    expect(r.data.error).not.toContain('FALTAN_OPCIONES');
  });

  it('una plantilla que no se edita dice POR QUÉ', async () => {
    rechazar(httpError(409, {
      error: 'NO_EDITABLE', detalle: 'Tiene cosas que el editor no maneja.',
      por_que_no: ["«Ok» es de tipo 'booleano'"]
    }));
    const r = await actions.publicar(peticion({ id: 'abc', definicion: '{"campos":[]}' }));
    expect(r.status).toBe(409);
    expect(r.data.error).toContain('booleano');
  });

  it('una definición rota no llega al backend', async () => {
    const r = await actions.publicar(peticion({ id: 'abc', definicion: '{no es json' }));
    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });
});

describe('adoptar y crear', () => {
  it('adoptar manda el código del catálogo y devuelve qué abrir', async () => {
    apiRequest.mockResolvedValue({ id: 'nuevo', nombre: 'Retiro de equipos' });
    const r = await actions.adoptar(peticion({ base: 'retiro_equipos' }));
    expect(apiRequest).toHaveBeenCalledWith(
      '/campo/plantillas/', { method: 'POST', body: { base: 'retiro_equipos' } }, { cookies });
    expect(r.abrir).toBe('nuevo');
  });

  it('un 403 de gestión llega con su texto y su estado', async () => {
    rechazar(httpError(403, {
      detail: 'Para armar cuadrillas hace falta un rol de gestion.' }));
    const r = await actions.adoptar(peticion({ base: 'retiro_equipos' }));
    expect(r.status).toBe(403);
    expect(r.data.error).toContain('rol de gestion');
  });
});

describe('load', () => {
  it('abre la plantilla de ?editar y no rompe la lista si esa falla', async () => {
    apiRequest.mockImplementation((/** @type {string} */ ruta) => {
      if (ruta === '/campo/plantillas/') return Promise.resolve({ propias: [{ id: 'x' }], catalogo: [] });
      throw httpError(404, { detail: 'No existe.' });
    });
    const d = await load(/** @type {any} */ ({
      url: new URL('http://x/supervisor-noc/plantillas?editar=otra'), cookies }));
    expect(d.propias).toHaveLength(1);
    expect(d.edicion).toBeNull();
    expect(d.edicionError).toBe('No existe.');
  });
});
