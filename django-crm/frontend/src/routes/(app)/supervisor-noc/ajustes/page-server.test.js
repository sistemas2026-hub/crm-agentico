import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * AJUSTES DEL SUPERVISOR: LO QUE LLEGA AL BACKEND (27/10/2026)
 * ============================================================
 *
 * Se afirma sobre el EFECTO: el cuerpo que recibe `cambiarTarea`, que es lo
 * que escribe el backend. Lo que tiene que pasar es que «quitar» viaje como
 * `delegar: false` —un booleano de verdad— y que sin motivo o sin rol no
 * viaje nada.
 *
 * Los módulos de servidor se sustituyen con `vi.mock`, como en
 * `cuadrillas/page-server.test.js`: la acción corre tal cual.
 */

const cambiarTarea = vi.fn();
const leerAjustes = vi.fn();

vi.mock('$lib/server/v2/ajustes-supervisor.js', () => ({
  leerAjustes: (/** @type {any[]} */ ...a) => leerAjustes(...a),
  cambiarTarea: (/** @type {any[]} */ ...a) => cambiarTarea(...a)
}));
//  Una zona que NO es Bogotá, a propósito: la pantalla fijaba Bogotá.
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({
  zonaDeLaEmpresa: async () => 'America/Lima'
}));

const { actions, load } = await import('./+page.server.js');

const JEFA = { profile: { role: 'OPERACIONES' } };

/** @param {Record<string, string>} campos @param {any} [locals] */
function evento(campos, locals = JEFA) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({
    request: new Request('http://x/supervisor-noc/ajustes?/cambiar', { method: 'POST', body: f }),
    cookies: {},
    locals
  });
}

beforeEach(() => {
  cambiarTarea.mockReset();
  leerAjustes.mockReset();
  cambiarTarea.mockResolvedValue({});
});

describe('el interruptor', () => {
  it('delegar viaja como true, con el motivo', async () => {
    await actions.cambiar(evento({ clave: 'armar_la_jornada_del_dia', delegar: 'si', motivo: ' ya se midió ' }));
    expect(cambiarTarea).toHaveBeenCalledWith(expect.anything(), {
      clave: 'armar_la_jornada_del_dia', delegar: true, motivo: 'ya se midió'
    });
  });

  it('quitar viaja como false, no como un texto', async () => {
    await actions.cambiar(evento({ clave: 'armar_la_jornada_del_dia', delegar: 'no', motivo: 'se equivoca' }));
    expect(cambiarTarea).toHaveBeenCalledWith(expect.anything(), {
      clave: 'armar_la_jornada_del_dia', delegar: false, motivo: 'se equivoca'
    });
  });

  it('un valor que no es si ni no, no viaja', async () => {
    const r = await actions.cambiar(evento({ clave: 'x', delegar: 'true', motivo: 'm' }));
    expect(cambiarTarea).not.toHaveBeenCalled();
    expect(/** @type {any} */ (r).status).toBe(400);
  });

  it('sin motivo no viaja', async () => {
    const r = await actions.cambiar(evento({ clave: 'x', delegar: 'si', motivo: '   ' }));
    expect(cambiarTarea).not.toHaveBeenCalled();
    expect(/** @type {any} */ (r).status).toBe(400);
  });

  it('sin rol de gestión no viaja', async () => {
    const r = await actions.cambiar(
      evento({ clave: 'x', delegar: 'si', motivo: 'm' }, { profile: { role: 'USER' } })
    );
    expect(cambiarTarea).not.toHaveBeenCalled();
    expect(/** @type {any} */ (r).status).toBe(403);
  });

  it('el 409 del backend llega a la fila con su frase', async () => {
    cambiarTarea.mockRejectedValue(
      Object.assign(new Error('x'), { status: 409, body: { detail: 'Esa tarea ya estaba delegada' } })
    );
    const r = /** @type {any} */ (
      await actions.cambiar(evento({ clave: 'armar_la_jornada_del_dia', delegar: 'si', motivo: 'm' }))
    );
    expect(r.status).toBe(409);
    expect(r.data.error).toContain('ya estaba delegada');
    expect(r.data.clave).toBe('armar_la_jornada_del_dia');
  });
});

describe('la carga', () => {
  it('sin rol de gestión no le pide nada al backend', async () => {
    const d = await load(/** @type {any} */ ({ cookies: {}, locals: { profile: { role: 'USER' } } }));
    expect(leerAjustes).not.toHaveBeenCalled();
    expect(/** @type {any} */ (d).puedeVer).toBe(false);
  });

  it('con rol, trae las tareas y la zona de la empresa para las fechas', async () => {
    leerAjustes.mockResolvedValue({ nivel_efectivo: 3, tareas: [{ clave: 'a' }] });
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ cookies: {}, locals: JEFA })));
    expect(d.ajustes.tareas).toHaveLength(1);
    expect(d.error).toBeNull();
    expect(d.zona).toBe('America/Lima');
  });
});
