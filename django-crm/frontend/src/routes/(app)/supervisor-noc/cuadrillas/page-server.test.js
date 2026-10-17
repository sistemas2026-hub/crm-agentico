import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * GUARDAR LA FICHA DE UNA CUADRILLA NO BORRA LO QUE NO SE TOCÓ
 * ============================================================
 *
 * EL DEFECTO, reportado por el usuario el 17/10/2026
 * --------------------------------------------------
 * «No deja seleccionar líder y después sale sin líder.» El selector de líder
 * no tenía al líder actual entre sus opciones; un `<select>` sin opción
 * elegida no viaja en el formulario, y la acción mandaba
 * `lider: f.get('lider') || null` = `null`. El backend escribe todo campo que
 * le llega (`CuadrillaView.patch`), así que le quitó el líder a la cuadrilla.
 * Las notas igual: la ficha no tiene ese campo y se mandaban vacías.
 *
 * QUÉ SE AFIRMA
 * -------------
 * Sobre el EFECTO: el cuerpo que recibe `editarCuadrilla`, que es lo que
 * escribe el backend. Cada prueba siembra también un campo que SÍ tiene que
 * viajar (el nombre, las zonas), para que un cuerpo vacío no pase por bueno.
 *
 * Los módulos de servidor se sustituyen con `vi.mock`, como en
 * `tickets/page-server.test.js`: la acción corre tal cual.
 */

const editarCuadrilla = vi.fn();
const crearCuadrilla = vi.fn();

vi.mock('$lib/server/v2/cuadrillas.js', () => {
  const nada = async () => ({});
  return {
    leerCuadrillas: nada,
    crearCuadrilla: (...a) => crearCuadrilla(...a),
    editarCuadrilla: (...a) => editarCuadrilla(...a),
    leerJornadaDeCuadrillas: nada,
    leerHistorialDeCuadrillas: nada,
    armarJornada: nada,
    leerZonas: nada,
    crearZona: nada,
    mapearZona: nada,
    leerLocalidades: nada,
    proponerReparto: nada,
    publicarReparto: nada,
    leerPersonasDeCampo: nada,
    crearPersonaDeCampo: nada,
    editarPersonaDeCampo: nada,
    leerConfiguracionDeReparto: nada,
    guardarConfiguracionDeReparto: nada,
    leerTiposDeTrabajo: nada,
    clasificarTipoDeTrabajo: nada
  };
});
vi.mock('$lib/server/v2/inventario.js', () => ({ leerUbicaciones: async () => ({}) }));

const { actions } = await import('./+page.server.js');

/**
 * El evento que SvelteKit armaría al enviar la ficha. `any` a propósito: un
 * RequestEvent real trae diez propiedades más que la acción nunca toca.
 *
 * @param {Record<string, string | string[]>} campos
 * @returns {any}
 */
function envio(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) {
    for (const x of [].concat(/** @type {any} */ (v))) f.append(k, x);
  }
  return {
    request: new Request('http://localhost/supervisor-noc/cuadrillas?/cuadrilla', {
      method: 'POST',
      body: f
    }),
    cookies: { get: () => 'token' }
  };
}

/** La ficha de una cuadrilla que YA tiene líder y vehículo. */
const FICHA = {
  cuadrilla_id: 'cu-2',
  nombre: 'Cuadrilla #2',
  lider_antes: 'pr-jeider',
  vehiculo_antes: 've-1',
  labor_habitual: 'correctivo',
  zona_habitual: ['zo-soledad']
};

/** El cuerpo con que se llamó a `editarCuadrilla`. */
function cuerpoEditado() {
  expect(editarCuadrilla).toHaveBeenCalledTimes(1);
  const [, id, cuerpo] = editarCuadrilla.mock.calls[0];
  expect(id).toBe('cu-2');
  return cuerpo;
}

beforeEach(() => {
  editarCuadrilla.mockReset().mockResolvedValue({ nombre: 'Cuadrilla #2' });
  crearCuadrilla.mockReset().mockResolvedValue({ nombre: 'Cuadrilla nueva' });
});

describe('la ficha de cuadrilla manda solo lo que la persona cambió', () => {
  it('EL DEFECTO: con el selector de líder sin opción elegida, el líder no se toca', async () => {
    // Sin `lider` ni `vehiculo`: así llega un <select> que no tenía la opción.
    await actions.cuadrilla(envio(FICHA));
    const cuerpo = cuerpoEditado();
    expect(cuerpo).not.toHaveProperty('lider');
    expect(cuerpo).not.toHaveProperty('vehiculo');
    // Lo que sí se marcó viaja: el cuerpo no salió vacío.
    expect(cuerpo.nombre).toBe('Cuadrilla #2');
    expect(cuerpo.zonas_habituales).toEqual(['zo-soledad']);
    expect(cuerpo.labor_habitual).toBe('correctivo');
  });

  it('el mismo líder que tenía no se vuelve a mandar', async () => {
    await actions.cuadrilla(envio({ ...FICHA, lider: 'pr-jeider', vehiculo: 've-1' }));
    const cuerpo = cuerpoEditado();
    expect(cuerpo).not.toHaveProperty('lider');
    expect(cuerpo).not.toHaveProperty('vehiculo');
  });

  it('«— sin líder —» elegido a propósito sí quita al líder', async () => {
    await actions.cuadrilla(envio({ ...FICHA, lider: '' }));
    expect(cuerpoEditado().lider).toBeNull();
  });

  it('otro líder elegido se manda', async () => {
    await actions.cuadrilla(envio({ ...FICHA, lider: 'pr-isaias', vehiculo: 've-2' }));
    const cuerpo = cuerpoEditado();
    expect(cuerpo.lider).toBe('pr-isaias');
    expect(cuerpo.vehiculo).toBe('ve-2');
  });

  it('las notas no se borran: la ficha no las trae y no se mandan', async () => {
    await actions.cuadrilla(envio({ ...FICHA, lider: 'pr-jeider' }));
    expect(cuerpoEditado()).not.toHaveProperty('notas');
  });

  it('si un formulario trae notas, se mandan', async () => {
    await actions.cuadrilla(envio({ ...FICHA, notas: 'Sale desde Soledad' }));
    expect(cuerpoEditado().notas).toBe('Sale desde Soledad');
  });

  it('una pantalla vieja, sin `lider_antes`, se comporta como antes', async () => {
    // La que quedó abierta en un navegador durante el deploy: sin el campo
    // de lo que ya tenía, lo que viaja se manda, igual que hasta hoy.
    const { lider_antes, ...vieja } = FICHA;
    await actions.cuadrilla(envio({ ...vieja, lider: 'pr-jeider' }));
    expect(cuerpoEditado().lider).toBe('pr-jeider');
  });

  it('al dar de alta, el líder elegido se manda', async () => {
    await actions.cuadrilla(envio({
      cuadrilla_id: '', nombre: 'Cuadrilla nueva', lider_antes: '', lider: 'pr-jeider',
      vehiculo_antes: '', vehiculo: ''
    }));
    expect(editarCuadrilla).not.toHaveBeenCalled();
    const [, cuerpo] = crearCuadrilla.mock.calls[0];
    expect(cuerpo.lider).toBe('pr-jeider');
    expect(cuerpo).not.toHaveProperty('vehiculo');
  });
});
