import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Plantillas desde Ajustes (28/10/2026): solo un administrador las manda a
 * revisión o las borra, y lo que se escribió en el formulario llega entero al
 * motor -- ejemplos y botones incluidos, que son lo que Meta revisa.
 */

const crearPlantilla = vi.fn();
const borrarPlantilla = vi.fn();
const listarPlantillas = vi.fn();
const cambiarUsoDePlantilla = vi.fn();
vi.mock('$lib/server/v2/canal-whatsapp.js', () => ({
  cambiarUsoDePlantilla: (...a) => cambiarUsoDePlantilla(...a),
  crearPlantilla: (...a) => crearPlantilla(...a),
  borrarPlantilla: (...a) => borrarPlantilla(...a),
  listarPlantillas: (...a) => listarPlantillas(...a)
}));

const { actions, load } = await import('./+page.server.js');

/** @param {Record<string, string | string[]>} campos @param {string} [rol] */
function evento(campos, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) {
    for (const x of Array.isArray(v) ? v : [v]) fd.append(k, x);
  }
  return /** @type {any} */ ({
    fetch: vi.fn(),
    request: { formData: async () => fd },
    locals: { profile: { role: rol } }
  });
}

const FORM = {
  nombre: ' encuesta_satisfaccion ',
  categoria: 'UTILITY',
  idioma: 'es',
  encabezado: '',
  cuerpo: 'Hola {{1}}, ¿cómo te atendimos?',
  pie: 'Gracias',
  ejemplo: ['Juan'],
  boton: ['Excelente', 'Buena', ' ', 'Mala']
};

describe('Plantillas de WhatsApp en Ajustes', () => {
  beforeEach(() => {
    crearPlantilla.mockReset();
    borrarPlantilla.mockReset();
    cambiarUsoDePlantilla.mockReset();
    listarPlantillas.mockReset();
  });

  it('la carga trae todas, y null si Meta no contestó (no "no hay")', async () => {
    listarPlantillas.mockResolvedValue(null);
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ fetch: vi.fn(), locals: { profile: { role: 'USER' } } })));
    expect(d.plantillas).toBeNull();
    expect(d.can_edit).toBe(false);
  });

  it('crear manda todo lo escrito: ejemplos y botones (sin los vacíos)', async () => {
    crearPlantilla.mockResolvedValue({ nombre: 'encuesta_satisfaccion', estado: 'PENDING', categoria: 'UTILITY' });
    const r = /** @type {any} */ (await actions.crear(evento(FORM)));
    expect(crearPlantilla.mock.calls[0][2]).toEqual({
      nombre: 'encuesta_satisfaccion',
      categoria: 'UTILITY',
      idioma: 'es',
      encabezado: '',
      cuerpo: 'Hola {{1}}, ¿cómo te atendimos?',
      pie: 'Gracias',
      ejemplos: ['Juan'],
      botones: ['Excelente', 'Buena', 'Mala']
    });
    expect(r.creada.estado).toBe('PENDING');
  });

  it('si Meta o el motor la rechazan, vuelve el motivo y lo escrito', async () => {
    crearPlantilla.mockRejectedValue(new Error('Cada variable necesita un ejemplo'));
    const r = /** @type {any} */ (await actions.crear(evento(FORM)));
    expect(r.status).toBe(400);
    expect(r.data.error).toMatch(/ejemplo/);
    expect(r.data.valores.cuerpo).toBe(FORM.cuerpo);
  });

  it('quien no es administrador no crea ni borra nada', async () => {
    expect((/** @type {any} */ (await actions.crear(evento(FORM, 'USER')))).status).toBe(403);
    expect((/** @type {any} */ (await actions.borrar(evento({ nombre: 'x' }, 'SUPERVISOR')))).status).toBe(403);
    expect(crearPlantilla).not.toHaveBeenCalled();
    expect(borrarPlantilla).not.toHaveBeenCalled();
  });

  it('desactivar una plantilla dice qué mensajes automáticos dejan de salir', async () => {
    cambiarUsoDePlantilla.mockResolvedValue({ en_uso: false, momentos_que_la_usan: ['seguimiento_ticket'] });
    const r = /** @type {any} */ (await actions.uso(evento({ nombre: 'seguimiento_caso', en_uso: '0' })));
    expect(cambiarUsoDePlantilla.mock.calls[0].slice(2)).toEqual(['seguimiento_caso', false]);
    expect(r.uso).toEqual({ nombre: 'seguimiento_caso', enUso: false, momentos: ['seguimiento_ticket'] });
  });

  it('activarla, y solo un administrador', async () => {
    cambiarUsoDePlantilla.mockResolvedValue({ en_uso: true, momentos_que_la_usan: [] });
    await actions.uso(evento({ nombre: 'seguimiento_caso', en_uso: '1' }));
    expect(cambiarUsoDePlantilla.mock.calls[0][3]).toBe(true);
    const r = /** @type {any} */ (await actions.uso(evento({ nombre: 'x', en_uso: '0' }, 'SUPERVISOR')));
    expect(r.status).toBe(403);
    expect(cambiarUsoDePlantilla).toHaveBeenCalledTimes(1);
  });

  it('borrar va por nombre', async () => {
    borrarPlantilla.mockResolvedValue(undefined);
    const r = /** @type {any} */ (await actions.borrar(evento({ nombre: 'seguimiento_caso' })));
    expect(borrarPlantilla.mock.calls[0][2]).toBe('seguimiento_caso');
    expect(r.borrada).toBe('seguimiento_caso');
  });
});
