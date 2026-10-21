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
const guardarConfiguracionDeReparto = vi.fn();
const guardarHorarioDeCuadrillas = vi.fn();

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
    guardarConfiguracionDeReparto: (...a) => guardarConfiguracionDeReparto(...a),
    leerHorarioDeCuadrillas: nada,
    guardarHorarioDeCuadrillas: (...a) => guardarHorarioDeCuadrillas(...a),
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

describe('la configuración del reparto manda la labor de cada caso solo si viene', () => {
  const LO_DE_SIEMPRE = { hora_local: '3', tope_por_cuadrilla: '8', copia_la_jornada: '1' };

  beforeEach(() => {
    guardarConfiguracionDeReparto.mockReset().mockResolvedValue({
      activo: false, hora_local: 3, tope_por_cuadrilla: 8
    });
  });

  it('con los cuatro selectores, viaja la tabla entera y «no cuenta» va vacío', async () => {
    await actions.reparto_config(envio({
      ...LO_DE_SIEMPRE,
      labor_de_falla_de_servicio: 'correctivo',
      labor_de_trabajo_pedido: 'correctivo',
      labor_de_instalacion_nueva: 'instalacion',
      labor_de_obra_de_red: ''
    }));
    const [, cuerpo] = guardarConfiguracionDeReparto.mock.calls[0];
    expect(cuerpo.labor_por_grupo).toEqual({
      falla_de_servicio: 'correctivo',
      trabajo_pedido: 'correctivo',
      instalacion_nueva: 'instalacion',
      obra_de_red: ''
    });
  });

  it('una pantalla de antes del 18/10, con tres selectores, no manda la fila nueva', async () => {
    //  La instalación de un cliente nuevo se partió del trabajo pedido el
    //  18/10/2026. Un formulario sin ese selector no la manda, y para esa
    //  fila vale la de fábrica en vez de un vacío que la sacaría de la cuenta.
    await actions.reparto_config(envio({
      ...LO_DE_SIEMPRE,
      labor_de_falla_de_servicio: 'correctivo',
      labor_de_trabajo_pedido: 'correctivo',
      labor_de_obra_de_red: 'trabajos'
    }));
    const [, cuerpo] = guardarConfiguracionDeReparto.mock.calls[0];
    expect(cuerpo.labor_por_grupo).not.toHaveProperty('instalacion_nueva');
    expect(cuerpo.labor_por_grupo.trabajo_pedido).toBe('correctivo');
  });

  it('el corte de red viaja si el formulario lo trae, y si no, no', async () => {
    await actions.reparto_config(envio({ ...LO_DE_SIEMPRE, onus_para_corte_de_red: '3' }));
    const [, con] = guardarConfiguracionDeReparto.mock.calls[0];
    expect(con.onus_para_corte_de_red).toBe('3');

    await actions.reparto_config(envio(LO_DE_SIEMPRE));
    const [, sin] = guardarConfiguracionDeReparto.mock.calls[1];
    expect(sin).not.toHaveProperty('onus_para_corte_de_red');
  });

  it('una pantalla vieja, sin los selectores, no manda la tabla y no la borra', async () => {
    await actions.reparto_config(envio(LO_DE_SIEMPRE));
    const [, cuerpo] = guardarConfiguracionDeReparto.mock.calls[0];
    expect(cuerpo).not.toHaveProperty('labor_por_grupo');
    expect(cuerpo.tope_por_cuadrilla).toBe('8');
  });
});

describe('el horario de las cuadrillas (21/10/2026)', () => {
  it('manda el horario ENTERO: los días sin «trabaja» viajan cerrados', async () => {
    guardarHorarioDeCuadrillas.mockReset().mockResolvedValue({ configurado: true });
    const r = /** @type {any} */ (await actions.horario(envio({
      zona_horaria: ' America/Bogota ',
      trabaja_lunes: '1', abre_lunes: '07:00', cierra_lunes: '17:00',
      abre_martes: '07:00', cierra_martes: '17:00',
      trabaja_sabado: '1', abre_sabado: '07:00', cierra_sabado: '12:00',
      feriados: '2026-12-08 Inmaculada Concepción\n\n  2026-12-25   Navidad  \n',
      hora_de_corte: '14:00'
    })));
    expect(guardarHorarioDeCuadrillas).toHaveBeenCalledTimes(1);
    const [, cuerpo] = guardarHorarioDeCuadrillas.mock.calls[0];
    expect(cuerpo.zona_horaria).toBe('America/Bogota');
    expect(cuerpo.hora_de_corte).toBe('14:00');
    expect(cuerpo.dias.lunes).toEqual({ abre: '07:00', cierra: '17:00' });
    //  Con horas escritas pero sin la casilla: cerrado.
    expect(cuerpo.dias.martes).toBeNull();
    expect(cuerpo.dias.sabado).toEqual({ abre: '07:00', cierra: '12:00' });
    expect(cuerpo.dias.domingo).toBeNull();
    expect(Object.keys(cuerpo.dias)).toHaveLength(7);
    expect(cuerpo.feriados).toEqual([
      { fecha: '2026-12-08', nombre: 'Inmaculada Concepción' },
      { fecha: '2026-12-25', nombre: 'Navidad' }
    ]);
    expect(r.hecho).toMatch(/Horario de las cuadrillas guardado/);
  });

  it('lo que el backend rechaza llega como su frase', async () => {
    guardarHorarioDeCuadrillas.mockReset().mockRejectedValue(
      Object.assign(new Error('x'), { status: 400, body: { detail: 'El lunes cierra antes de abrir.' } })
    );
    const r = /** @type {any} */ (await actions.horario(envio({ zona_horaria: 'America/Bogota' })));
    expect(r.status).toBe(400);
    expect(r.data.error).toContain('cierra antes de abrir');
  });
});
