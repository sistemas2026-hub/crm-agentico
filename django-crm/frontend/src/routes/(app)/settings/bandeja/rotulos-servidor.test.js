import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Los rótulos de la Bandeja (29/10/2026): el formulario manda un campo por
 * clave (`rotulo:<clave>`), y lo que llega al motor tiene que ser el mapa
 * clave → texto sin los vacíos. Es el salto donde un nombre de campo mal
 * cortado haría que el motor rechace todo o, peor, guarde la clave con el
 * prefijo pegado. Solo un administrador escribe.
 */

const guardarRotulosBandeja = vi.fn();
const leerRotulosBandeja = vi.fn();
const leerAjustesBandeja = vi.fn();
const guardarReincidencia = vi.fn();
const guardarEtiquetasDelEquipo = vi.fn();
vi.mock('$lib/server/v2/bandeja-config.js', () => ({
  guardarAjustesBandeja: vi.fn(),
  leerAjustesBandeja: (...a) => leerAjustesBandeja(...a),
  guardarRotulosBandeja: (...a) => guardarRotulosBandeja(...a),
  leerRotulosBandeja: (...a) => leerRotulosBandeja(...a),
  guardarReincidencia: (...a) => guardarReincidencia(...a),
  // Las respuestas rápidas (11/11/2026) se cargan en el mismo load; tienen su
  // propia prueba en respuestas-servidor.test.js.
  leerRespuestasRapidas: async () => [],
  guardarRespuestasRapidas: vi.fn(),
  guardarEtiquetasDelEquipo: (...a) => guardarEtiquetasDelEquipo(...a)
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

describe('rótulos de la Bandeja', () => {
  beforeEach(() => {
    guardarRotulosBandeja.mockReset();
    leerRotulosBandeja.mockReset();
    leerAjustesBandeja.mockReset();
  });

  it('la carga trae los rótulos junto a los ajustes', async () => {
    leerAjustesBandeja.mockResolvedValue({ sla_toma_minutos: 0 });
    leerRotulosBandeja.mockResolvedValue({ claves: { motivos: ['queja'] }, rotulos: {} });
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ fetch: vi.fn(), locals: {} })));
    expect(d.rotulos.claves.motivos).toEqual(['queja']);
  });

  it('manda el mapa clave → texto, sin el prefijo y sin los vacíos', async () => {
    guardarRotulosBandeja.mockResolvedValue({});
    const r = /** @type {any} */ (await actions.rotulos(evento({
      'rotulo:frustracion_detectada': '  Frustración detectada ',
      'rotulo:queja': '',
      otro_campo: 'no es un rótulo'
    })));
    expect(guardarRotulosBandeja.mock.calls[0][2]).toEqual({
      frustracion_detectada: 'Frustración detectada'
    });
    expect(r.rotulosGuardados).toBe(true);
  });

  it('el error del motor llega tal cual', async () => {
    guardarRotulosBandeja.mockRejectedValue(new Error("'x' no es un motivo"));
    const r = /** @type {any} */ (await actions.rotulos(evento({ 'rotulo:x': 'Algo' })));
    expect(r.status).toBe(400);
    expect(r.data.rotulos.error).toMatch(/no es un motivo/);
  });

  it('los días de reincidencia llegan como número', async () => {
    guardarReincidencia.mockReset().mockResolvedValue({});
    const r = /** @type {any} */ (await actions.reincidencia(evento({ reincidencia_dias: '15' })));
    expect(guardarReincidencia.mock.calls[0][2]).toBe(15);
    expect(r.reincidenciaGuardada).toBe(true);
  });

  it('fuera de rango no llega al motor', async () => {
    guardarReincidencia.mockReset();
    const r = /** @type {any} */ (await actions.reincidencia(evento({ reincidencia_dias: '900' })));
    expect(r.status).toBe(400);
    expect(guardarReincidencia).not.toHaveBeenCalled();
  });

  it('quien no es administrador no escribe', async () => {
    const r = /** @type {any} */ (await actions.rotulos(evento({ 'rotulo:queja': 'Queja' }, 'USER')));
    expect(r.status).toBe(403);
    expect(guardarRotulosBandeja).not.toHaveBeenCalled();
  });
});

/* Las etiquetas del equipo (11/11/2026): el campo oculto con la lista entera
   tiene que llegar al motor con clave/nombre/color y NADA más, y una lista
   malformada no puede llegar. */
describe('etiquetas del equipo', () => {
  // Con llaves: lo que devuelve un beforeEach, vitest lo llama como limpieza
  // al terminar cada prueba -- y devolver el mock lo invocaba de más.
  beforeEach(() => {
    guardarEtiquetasDelEquipo.mockReset().mockResolvedValue({});
  });

  it('la lista llega entera; la nueva sin clave, la renombrada con la suya', async () => {
    const r = /** @type {any} */ (await actions.etiquetas(evento({
      etiquetas: JSON.stringify([
        { clave: 'vip', nombre: ' Muy importante ', color: 'amarillo', extra: 'no viaja' },
        { clave: '', nombre: 'Nueva', color: 'verde' }
      ])
    })));
    expect(r.etiquetasGuardadas).toBe(true);
    expect(guardarEtiquetasDelEquipo.mock.calls[0][2]).toEqual([
      { clave: 'vip', nombre: 'Muy importante', color: 'amarillo' },
      { nombre: 'Nueva', color: 'verde' }
    ]);
  });

  it('una lista vacía se manda vacía: es borrarlas todas', async () => {
    await actions.etiquetas(evento({ etiquetas: '[]' }));
    expect(guardarEtiquetasDelEquipo.mock.calls[0][2]).toEqual([]);
  });

  it('un JSON roto o una sin nombre no llegan al motor', async () => {
    const roto = /** @type {any} */ (await actions.etiquetas(evento({ etiquetas: '{no' })));
    const sinNombre = /** @type {any} */ (await actions.etiquetas(evento({
      etiquetas: JSON.stringify([{ nombre: '  ', color: 'gris' }])
    })));
    expect(roto.status).toBe(400);
    expect(sinNombre.status).toBe(400);
    expect(guardarEtiquetasDelEquipo).not.toHaveBeenCalled();
  });

  it('el error del motor llega tal cual', async () => {
    guardarEtiquetasDelEquipo.mockRejectedValue(new Error("'#f0a' no es uno de los colores"));
    const r = /** @type {any} */ (await actions.etiquetas(evento({
      etiquetas: JSON.stringify([{ nombre: 'X', color: '#f0a' }])
    })));
    expect(r.status).toBe(400);
    expect(r.data.etiquetas.error).toMatch(/colores/);
  });

  it('quien no es administrador no escribe', async () => {
    const r = /** @type {any} */ (await actions.etiquetas(evento({ etiquetas: '[]' }, 'USER')));
    expect(r.status).toBe(403);
    expect(guardarEtiquetasDelEquipo).not.toHaveBeenCalled();
  });
});
