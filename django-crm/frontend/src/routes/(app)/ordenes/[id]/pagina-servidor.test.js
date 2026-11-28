import { describe, it, expect, vi, beforeEach } from 'vitest';

/*
 * La página de una orden (12/11/2026): el gate de rol y lo que recibe la
 * página, atravesando el load y las capas servidor hasta la respuesta del
 * backend simulada por URL.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load } = await import('./+page.server.js');

const ORDEN = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const CASO = '11111111-2222-3333-4444-555555555555';

const HILO = {
  id: ORDEN, numero: 188, tipo: 'Correctivo', estado_operativo: 'en_sitio',
  estado_etiqueta: 'En sitio', caso: { id: CASO, nombre: 'Sin internet' }, servicio: '4986',
  cuadrilla_integrantes: [{ nombre: 'Carlos', rol: 'Técnico', es_principal: true }],
  evidencias: []
};
//  Un AVANCE sin INICIO: válido, y el backend lo marca en `avisos`.
const SEGUIMIENTO = {
  eventos: [{ id: 'e1', tipo: 'seguimiento_avance', etiqueta: 'Avance' }],
  avisos: ['Hay avances reportados sin un INICIO: falta la condición inicial.'],
  bloqueo_abierto: null
};
const MATERIALES = { hay_algo: true, consumido: [{ id: 'm1', material: { nombre: 'Conector' } }] };

function porUrl() {
  apiRequest.mockImplementation(async (/** @type {string} */ url) => {
    if (url.endsWith('/hilo/')) return HILO;
    if (url.endsWith('/seguimiento/')) return SEGUIMIENTO;
    if (url.includes('/materiales/')) return MATERIALES;
    throw Object.assign(new Error('?'), { status: 500 });
  });
}

/** @param {string} rol */
const evento = (rol) => /** @type {any} */ ({
  params: { id: ORDEN },
  cookies: {},
  locals: { user: { id: 1 }, profile: { role: rol } },
  fetch: vi.fn()
});

beforeEach(() => {
  apiRequest.mockReset();
});

describe('la página de la orden', () => {
  it('un rol que no es de gestión recibe 403 y no se consulta nada', async () => {
    await expect(load(evento('USER'))).rejects.toMatchObject({ status: 403 });
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('la gestión recibe el hilo, la bitácora con su anomalía y el material', async () => {
    porUrl();
    const d = /** @type {any} */ (await load(evento('OPERACIONES')));
    expect(d.orden).toEqual(HILO);
    expect(d.seguimiento.avisos[0]).toMatch(/sin un INICIO/);
    // El orden de la bitácora es el del backend: nadie lo toca en el camino.
    expect(d.seguimiento.eventos).toEqual(SEGUIMIENTO.eventos);
    expect(d.materiales).toEqual(MATERIALES);
    expect(await d.conversacion).toBeNull();
  });

  it('una orden de otra empresa (404 del backend) es una página 404', async () => {
    apiRequest.mockImplementation(async () => {
      throw Object.assign(new Error('x'), { status: 404 });
    });
    await expect(load(evento('ADMIN'))).rejects.toMatchObject({ status: 404 });
  });
});
