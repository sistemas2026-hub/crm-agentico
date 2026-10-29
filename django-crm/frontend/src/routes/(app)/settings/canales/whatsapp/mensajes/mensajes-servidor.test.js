import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Mensajes automáticos (28/10/2026): solo un administrador cambia, los datos
 * viajan EN ORDEN (el primero es {{1}}), y uno sin elegir no se manda: la
 * pantalla del CRM anterior dejaba guardar a medias y el envío fallaba con el
 * cliente.
 */

const guardarMensajeAutomatico = vi.fn();
const leerMensajesAutomaticos = vi.fn();
vi.mock('$lib/server/v2/canal-whatsapp.js', () => ({
  guardarMensajeAutomatico: (...a) => guardarMensajeAutomatico(...a),
  leerMensajesAutomaticos: (...a) => leerMensajesAutomaticos(...a)
}));

const { actions, load } = await import('./+page.server.js');

/** @param {Record<string, string | string[]>} campos @param {string} [rol] */
function evento(campos, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) for (const x of Array.isArray(v) ? v : [v]) fd.append(k, x);
  return /** @type {any} */ ({ fetch: vi.fn(), request: { formData: async () => fd }, locals: { profile: { role: rol } } });
}

describe('Mensajes automáticos', () => {
  beforeEach(() => {
    guardarMensajeAutomatico.mockReset();
    leerMensajesAutomaticos.mockReset();
  });

  it('la carga dice si puede editar', async () => {
    leerMensajesAutomaticos.mockResolvedValue({ eventos: [] });
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ fetch: vi.fn(), locals: { profile: { role: 'USER' } } })));
    expect(d.can_edit).toBe(false);
  });

  it('guarda el momento con los datos en orden y el interruptor', async () => {
    guardarMensajeAutomatico.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.guardar(evento({
      evento: 'ticket_creado_cliente', plantilla: 'ticket_creado', activo: 'on',
      dato: ['cliente_nombre', 'ticket_numero']
    })));
    expect(guardarMensajeAutomatico.mock.calls[0][2]).toBe('ticket_creado_cliente');
    expect(guardarMensajeAutomatico.mock.calls[0][3]).toEqual({
      activo: true, plantilla: 'ticket_creado', datos: ['cliente_nombre', 'ticket_numero']
    });
    expect(r.guardado).toBe('ticket_creado_cliente');
  });

  it('un lugar sin dato no se manda al motor', async () => {
    const r = /** @type {any} */ (await actions.guardar(evento({
      evento: 'ticket_creado_cliente', plantilla: 'ticket_creado', dato: ['cliente_nombre', '']
    })));
    expect(r.status).toBe(400);
    expect(guardarMensajeAutomatico).not.toHaveBeenCalled();
  });

  it('el motivo del motor vuelve, atado a su momento', async () => {
    guardarMensajeAutomatico.mockRejectedValue(new Error('La plantilla pide 2 dato(s) y elegiste 1.'));
    const r = /** @type {any} */ (await actions.guardar(evento({
      evento: 'bienvenida', plantilla: 'x', activo: 'on', dato: ['cliente_nombre']
    })));
    expect(r.status).toBe(400);
    expect(r.data).toEqual({ evento: 'bienvenida', error: 'La plantilla pide 2 dato(s) y elegiste 1.' });
  });

  it('el interruptor enciende al instante con lo ya guardado', async () => {
    guardarMensajeAutomatico.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.encender(evento({
      evento: 'seguimiento_ticket', activo: '1', plantilla: 'seguimiento_caso', dato: ['cliente_nombre', 'escrito']
    })));
    expect(guardarMensajeAutomatico.mock.calls[0][3]).toEqual({
      activo: true, plantilla: 'seguimiento_caso', datos: ['cliente_nombre', 'escrito']
    });
    expect(r.guardado).toBe('seguimiento_ticket');
  });

  it('apagar no exige datos completos; encender incompleto lo rechaza el motor y se dice', async () => {
    guardarMensajeAutomatico.mockResolvedValue({});
    await actions.encender(evento({ evento: 'bienvenida', activo: '0', plantilla: '' }));
    expect(guardarMensajeAutomatico.mock.calls[0][3]).toEqual({ activo: false, plantilla: '', datos: [] });
    guardarMensajeAutomatico.mockRejectedValue(new Error('Para encenderlo, la plantilla tiene que estar aprobada por Meta.'));
    const r = /** @type {any} */ (await actions.encender(evento({ evento: 'bienvenida', activo: '1', plantilla: '' })));
    expect(r.status).toBe(400);
    expect(r.data.evento).toBe('bienvenida');
  });

  it('el interruptor tampoco lo usa quien no es administrador', async () => {
    const r = /** @type {any} */ (await actions.encender(evento({ evento: 'bienvenida', activo: '1' }, 'USER')));
    expect(r.status).toBe(403);
  });

  it('quien no es administrador no cambia nada', async () => {
    const r = /** @type {any} */ (await actions.guardar(evento({ evento: 'bienvenida' }, 'SUPERVISOR')));
    expect(r.status).toBe(403);
    expect(guardarMensajeAutomatico).not.toHaveBeenCalled();
  });
});
