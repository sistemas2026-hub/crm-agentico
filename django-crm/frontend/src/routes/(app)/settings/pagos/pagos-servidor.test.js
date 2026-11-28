import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La pantalla de Pagos: solo un administrador escribe, y lo que escribe es lo
 * que llega al puente (el campo `link_de_pago`, o las filas `medio_nombre` /
 * `medio_instruccion` del formulario).
 */
const guardarLinkDePago = vi.fn();
const guardarMediosDePago = vi.fn();
const leerAjustesDePago = vi.fn();
vi.mock('$lib/server/v2/pagos-config.js', () => ({
  guardarLinkDePago: (...a) => guardarLinkDePago(...a),
  guardarMediosDePago: (...a) => guardarMediosDePago(...a),
  leerAjustesDePago: (...a) => leerAjustesDePago(...a)
}));

const { actions, load } = await import('./+page.server.js');

/** @param {Array<[string, string]>} campos @param {string} [rol] */
function evento(campos, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of campos) fd.append(k, v);
  return /** @type {any} */ ({
    fetch: vi.fn(),
    request: { formData: async () => fd },
    locals: { profile: { role: rol } }
  });
}

describe('Ajustes → Pagos', () => {
  beforeEach(() => {
    guardarLinkDePago.mockReset();
    guardarMediosDePago.mockReset();
    leerAjustesDePago.mockReset();
  });

  it('la carga trae lo cargado y dice si se puede editar', async () => {
    const cargado = { link: 'https://pagos.ejemplo.co', medios: [{ nombre: 'Efecty', instruccion: 'Convenio 1' }], medios_ilegibles: false };
    leerAjustesDePago.mockResolvedValue(cargado);
    const d = /** @type {any} */ (
      await load(/** @type {any} */ ({ fetch: vi.fn(), locals: { profile: { role: 'ADMIN' } } }))
    );
    expect(d.ajustes).toEqual(cargado);
    expect(d.can_edit).toBe(true);
    const e = /** @type {any} */ (
      await load(/** @type {any} */ ({ fetch: vi.fn(), locals: { profile: { role: 'USER' } } }))
    );
    expect(e.can_edit).toBe(false);
  });

  it('un administrador guarda el link: el campo del formulario llega al puente', async () => {
    guardarLinkDePago.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.guardar(evento([['link_de_pago', 'https://pagos.ejemplo.co']])));
    expect(guardarLinkDePago.mock.calls[0][2]).toBe('https://pagos.ejemplo.co');
    expect(r.guardado).toBe(true);
  });

  it('quien no es administrador NO guarda el link, y no se llama al puente', async () => {
    const r = /** @type {any} */ (await actions.guardar(evento([['link_de_pago', 'https://x.co']], 'USER')));
    expect(r.status).toBe(403);
    expect(guardarLinkDePago).not.toHaveBeenCalled();
  });

  it('si el puente rechaza el link, el mensaje llega a la pantalla', async () => {
    guardarLinkDePago.mockRejectedValue(new Error('El link tiene que empezar con https://'));
    const r = /** @type {any} */ (await actions.guardar(evento([['link_de_pago', 'http://x.co']])));
    expect(r.status).toBe(400);
    expect(r.data.guardar.error).toMatch(/https/);
  });

  it('un administrador guarda los medios: cada fila llega al puente, emparejada por posición', async () => {
    guardarMediosDePago.mockResolvedValue({});
    const r = /** @type {any} */ (
      await actions.guardar_medios(
        evento([
          ['medio_nombre', 'Efecty'],
          ['medio_instruccion', 'Convenio 12345. Di tu cédula.'],
          ['medio_nombre', 'Banco'],
          ['medio_instruccion', 'Cuenta 000']
        ])
      )
    );
    expect(guardarMediosDePago.mock.calls[0][2]).toEqual([
      { nombre: 'Efecty', instruccion: 'Convenio 12345. Di tu cédula.' },
      { nombre: 'Banco', instruccion: 'Cuenta 000' }
    ]);
    expect(r.guardado_medios).toBe(true);
  });

  it('sin filas en el formulario llega una lista vacía (quitar todos), no un error', async () => {
    guardarMediosDePago.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.guardar_medios(evento([])));
    expect(guardarMediosDePago.mock.calls[0][2]).toEqual([]);
    expect(r.guardado_medios).toBe(true);
  });

  it('quien no es administrador NO guarda los medios, y no se llama al puente', async () => {
    const r = /** @type {any} */ (
      await actions.guardar_medios(evento([['medio_nombre', 'X'], ['medio_instruccion', 'y']], 'USER'))
    );
    expect(r.status).toBe(403);
    expect(guardarMediosDePago).not.toHaveBeenCalled();
  });

  it('si el puente rechaza los medios, el mensaje llega a la pantalla del bloque de medios', async () => {
    guardarMediosDePago.mockRejectedValue(new Error('Al medio "Efecty" le falta decir cómo se paga'));
    const r = /** @type {any} */ (
      await actions.guardar_medios(evento([['medio_nombre', 'Efecty'], ['medio_instruccion', '']]))
    );
    expect(r.status).toBe(400);
    expect(r.data.guardar_medios.error).toMatch(/Efecty/);
    expect(r.data.guardar).toBeUndefined();
  });
});
