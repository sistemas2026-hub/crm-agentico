import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La pantalla de Pagos: solo un administrador escribe, y lo que escribe es lo
 * que llega al puente (el campo `link_de_pago` del formulario).
 */
const guardarLinkDePago = vi.fn();
const leerLinkDePago = vi.fn();
vi.mock('$lib/server/v2/pagos-config.js', () => ({
  guardarLinkDePago: (...a) => guardarLinkDePago(...a),
  leerLinkDePago: (...a) => leerLinkDePago(...a)
}));

const { actions, load } = await import('./+page.server.js');

/** @param {Record<string, string>} campos @param {string} [rol] */
function evento(campos, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.append(k, v);
  return /** @type {any} */ ({
    fetch: vi.fn(),
    request: { formData: async () => fd },
    locals: { profile: { role: rol } }
  });
}

describe('Ajustes → Pagos', () => {
  beforeEach(() => {
    guardarLinkDePago.mockReset();
    leerLinkDePago.mockReset();
  });

  it('la carga trae el link y dice si se puede editar', async () => {
    leerLinkDePago.mockResolvedValue({ link: 'https://pagos.ejemplo.co' });
    const d = /** @type {any} */ (
      await load(/** @type {any} */ ({ fetch: vi.fn(), locals: { profile: { role: 'ADMIN' } } }))
    );
    expect(d.ajustes).toEqual({ link: 'https://pagos.ejemplo.co' });
    expect(d.can_edit).toBe(true);
    const e = /** @type {any} */ (
      await load(/** @type {any} */ ({ fetch: vi.fn(), locals: { profile: { role: 'USER' } } }))
    );
    expect(e.can_edit).toBe(false);
  });

  it('un administrador guarda: el campo del formulario llega al puente', async () => {
    guardarLinkDePago.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.guardar(evento({ link_de_pago: 'https://pagos.ejemplo.co' })));
    expect(guardarLinkDePago.mock.calls[0][2]).toBe('https://pagos.ejemplo.co');
    expect(r.guardado).toBe(true);
  });

  it('quien no es administrador NO guarda, y no se llama al puente', async () => {
    const r = /** @type {any} */ (await actions.guardar(evento({ link_de_pago: 'https://x.co' }, 'USER')));
    expect(r.status).toBe(403);
    expect(guardarLinkDePago).not.toHaveBeenCalled();
  });

  it('si el puente rechaza, el mensaje llega a la pantalla', async () => {
    guardarLinkDePago.mockRejectedValue(new Error('El link tiene que empezar con https://'));
    const r = /** @type {any} */ (await actions.guardar(evento({ link_de_pago: 'http://x.co' })));
    expect(r.status).toBe(400);
    expect(r.data.guardar.error).toMatch(/https/);
  });
});
