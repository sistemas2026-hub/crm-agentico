import { describe, it, expect, vi } from 'vitest';

/**
 * LA COLA LEE EL AREA DEL CASO, NO LA DE QUIEN LO TIENE ASIGNADO
 * ==============================================================
 *
 * EL DEFECTO, medido en local el 16/10/2026
 * -----------------------------------------
 *
 *     Case.area = soporte_tecnico       65
 *     pantalla "Soporte Técnico"        64
 *     pantalla "Sin área asignada"       6
 *
 * El que faltaba --"Sin internet, LOS en rojo"-- tenia area 'soporte_tecnico'
 * y estaba asignado a alguien sin area en el motor, asi que la pantalla lo
 * mandaba a "Sin área asignada". Y lo grave, al reves: un ticket de ventas
 * asignado a un tecnico aparecia como Soporte Tecnico -- el defecto que el
 * Supervisor NOC ya no tiene (cdaa9b27), vivo en esta pantalla.
 *
 * QUE SE AFIRMA
 * -------------
 * Sobre el EFECTO del `load`, que es lo unico que decide que ve la persona:
 * que tickets quedan en `tickets`, que piden los parametros al API, y que
 * dicen las tarjetas. Se siembra siempre el ticket que tiene que quedar
 * AFUERA junto al que tiene que quedar ADENTRO: una cola vacia tambien seria
 * verde sin el de control.
 *
 * COMO SE LLEGA AL `load`
 * -----------------------
 * `vitest.config.js` no resuelve `$env/dynamic/private`, que `areas.js`
 * importa a nivel de modulo. Por eso los modulos de servidor se sustituyen
 * enteros con `vi.mock`: el `load` corre tal cual, y lo que esta detras del
 * API y del motor viene fijo de aca. `filter-params.js` y `paginacion.js`
 * son los reales.
 */

const PERSONAS = [
  { id: 'p-admin', email: 'admin@x.test', name: 'Admin' },
  { id: 'p-soporte', email: 'tecnico@x.test', name: 'Técnico' },
  { id: 'p-cartera', email: 'cartera@x.test', name: 'Cartera' },
  { id: 'p-nuevo', email: 'nuevo@x.test', name: 'Nuevo' }
];

const AREAS = [
  { nombre: 'cartera', etiqueta: 'Cartera' },
  { nombre: 'soporte_tecnico', etiqueta: 'Soporte Técnico' },
  { nombre: 'administracion', etiqueta: 'Administración' }
];

/** El mapa del motor: 'p-nuevo' no tiene area, como el responsable del LOS. */
const MAPA = { 'p-soporte': 'soporte_tecnico', 'p-cartera': 'cartera', 'p-admin': 'administracion' };

const listTickets = vi.fn();
const tomarTicket = vi.fn();
vi.mock('$lib/server/v2/tickets.js', () => ({
  listTickets: (...args) => listTickets(...args),
  tomarTicket: (...args) => tomarTicket(...args),
  OPEN_STATUSES: ['New', 'Assigned', 'Pending'],
  FILTER_FIELDS: ['assigned_to', 'priority', 'case_type', 'sla_breached', 'tags']
}));
vi.mock('$lib/server/v2/areas.js', () => ({
  leerAreas: async () => ({ areas: AREAS, areaPorPersona: MAPA })
}));
vi.mock('$lib/server/v2/org-people.js', () => ({
  getOrgPeopleAndTeams: async () => ({ people: PERSONAS, teams: [] }),
  resolveMe: (people, email) => people.find((p) => p.email === email)?.id ?? null
}));
vi.mock('$lib/server/v2/tags.js', () => ({ getTags: async () => ({ tags: [] }) }));

const { load, actions } = await import('./+page.server.js');

/** Una fila como la deja el modelador de tickets.js. */
function ticket(id, { area = '', assignee = null, name = 'No tiene internet' } = {}) {
  return {
    id, name, status: 'New', priority: 'Normal', area,
    assignee_id: assignee, assignee: assignee, assignee_count: assignee ? 1 : 0,
    is_open: true
  };
}

/**
 * Lo que devuelve el API cuando NO filtra nada: el `load` tiene que recortar
 * igual, porque es lo que decide que viaja al navegador.
 */
const LOS = ticket('los', { area: 'soporte_tecnico', assignee: 'p-nuevo', name: 'Sin internet, LOS en rojo' });
const VENTAS_DEL_TECNICO = ticket('ventas', { area: 'ventas', assignee: 'p-soporte', name: 'Cotización plan nuevo' });
const DE_SOPORTE = ticket('propio', { area: 'soporte_tecnico', assignee: 'p-soporte' });
const VIEJO_DEL_TECNICO = ticket('viejo', { area: '', assignee: 'p-soporte' });
const VIEJO_DE_CARTERA = ticket('viejo-cartera', { area: '', assignee: 'p-cartera' });
const SUELTO_SIN_NADA = ticket('suelto', { area: '', assignee: null });

const TODOS = [LOS, VENTAS_DEL_TECNICO, DE_SOPORTE, VIEJO_DEL_TECNICO, VIEJO_DE_CARTERA, SUELTO_SIN_NADA];

/** El desglose del backend, por (area, responsable), sobre los mismos seis. */
const DESGLOSE = [
  { area: 'soporte_tecnico', assigned_to: 'p-nuevo', total: 1, urgentes: 0, sin_respuesta: 1, en_progreso: 0 },
  { area: 'ventas', assigned_to: 'p-soporte', total: 1, urgentes: 0, sin_respuesta: 1, en_progreso: 0 },
  { area: 'soporte_tecnico', assigned_to: 'p-soporte', total: 1, urgentes: 0, sin_respuesta: 1, en_progreso: 0 },
  { area: '', assigned_to: 'p-soporte', total: 1, urgentes: 0, sin_respuesta: 1, en_progreso: 0 },
  { area: '', assigned_to: 'p-cartera', total: 1, urgentes: 0, sin_respuesta: 1, en_progreso: 0 },
  { area: '', assigned_to: null, total: 1, urgentes: 0, sin_respuesta: 1, en_progreso: 0 }
];

function respuesta(results = TODOS) {
  return {
    results,
    openByAssignee: DESGLOSE,
    totals: { count: results.length, open: results.length, urgent: 0, awaiting_reply: 0, shown: results.length }
  };
}

/**
 * El evento que SvelteKit armaria, con lo que esta ruta lee. Tipado `any` a
 * proposito: un RequestEvent real trae diez propiedades mas que el `load`
 * nunca toca.
 * @returns {any}
 */
function evento(query, { rol = 'ADMIN', email = 'admin@x.test' } = {}) {
  return {
    cookies: { get: () => 'token' },
    url: new URL(`http://localhost/tickets${query}`),
    locals: { profile: { role: rol }, user: { email } },
    fetch: async () => new Response('{}')
  };
}

const ids = (data) => data.tickets.map((t) => t.id);

describe('la cola de Soporte Técnico, vista por quien administra', () => {
  it('EL EFECTO: el ticket de soporte asignado a alguien sin area SI esta', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento('?area=soporte_tecnico'));
    expect(ids(data)).toContain('los');
  });

  it('y el de ventas asignado al tecnico NO esta', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento('?area=soporte_tecnico'));
    expect(ids(data)).not.toContain('ventas');
  });

  it('la cola completa: soporte escrito, mas los viejos sin area del tecnico', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento('?area=soporte_tecnico'));
    expect(ids(data).sort()).toEqual(['los', 'propio', 'viejo']);
  });

  it('le pide al API el area escrita, y la gente del area aparte para los viejos', async () => {
    listTickets.mockResolvedValue(respuesta());
    await load(evento('?area=soporte_tecnico'));
    const params = listTickets.mock.lastCall[1];
    expect(params.get('area')).toBe('soporte_tecnico');
    expect(params.getAll('area_responsables')).toEqual(['p-soporte']);
    //  El area ya NO viaja disfrazada de responsable: eso es lo que hacia que
    //  un ticket de ventas del tecnico llegara a esta cola.
    expect(params.has('assigned_to')).toBe(false);
  });

  it('elegir un responsable en la barra se cruza con el area, no la reemplaza', async () => {
    //  La barra manda un id real: readFilters descarta lo que no sea un UUID.
    const CARTERA = '11111111-2222-4333-8444-555555555555';
    listTickets.mockResolvedValue(respuesta());
    await load(evento(`?area=soporte_tecnico&assigned_to=${CARTERA}`));
    const params = listTickets.mock.lastCall[1];
    expect(params.getAll('assigned_to')).toEqual([CARTERA]);
    expect(params.get('area')).toBe('soporte_tecnico');
  });
});

describe('las tarjetas', () => {
  it('Soporte Técnico cuenta el LOS, no lo manda a "Sin área asignada"', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento(''));
    const soporte = data.areas.find((a) => a.nombre === 'soporte_tecnico');
    //  el LOS, el propio, y el viejo del tecnico por la mitad vieja
    expect(soporte.total).toBe(3);
  });

  it('Ventas existe como tarjeta aunque la config no la declare, y no suma en Soporte', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento(''));
    expect(data.areas.find((a) => a.nombre === 'ventas')?.total).toBe(1);
  });

  it('"Sin área asignada" queda solo con el suelto sin area ni responsable', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento(''));
    expect(data.areas.find((a) => a.nombre === data.sinArea)?.total).toBe(1);
  });

  it('el aviso de responsables sin area NO nombra a quien solo tiene casos con area escrita', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento(''));
    expect(data.sinAreaConfigurada).toEqual([]);
  });
});

describe('un colaborador de soporte, que solo ve su area', () => {
  //  20/10/2026, decidido por el usuario: lo que tiene asignado lo ve
  //  siempre. Hasta ese dia esta prueba afirmaba lo contrario --"no ve el de
  //  ventas, aunque sea suyo"--, y con el area escrita en cada caso eso
  //  sacaba de su lista los tickets que le tocan.
  it('ve el LOS y TAMBIEN el de ventas que es suyo, y no el viejo de cartera', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('?area=soporte_tecnico', { rol: 'USER', email: 'tecnico@x.test' })));
    expect(ids(data)).toContain('los');
    expect(ids(data)).toContain('ventas');
    expect(ids(data)).not.toContain('viejo-cartera');
    expect(data.deOtrasAreas).toBe(1);
  });

  it('ve el de otra area donde es el SEGUNDO responsable', async () => {
    //  Auditor independiente, 20/10/2026: 'mios' miraba solo el primero.
    const segundo = {
      ...ticket('segundo', { area: 'ventas', assignee: 'p-cartera' }),
      assignee_ids: ['p-cartera', 'p-soporte'], assignee_count: 2
    };
    listTickets.mockResolvedValue(respuesta([...TODOS, segundo]));
    const data = /** @type {any} */ (await load(evento('?area=soporte_tecnico', { rol: 'USER', email: 'tecnico@x.test' })));
    expect(ids(data)).toContain('segundo');
    expect(data.deOtrasAreas).toBe(2);
  });

  it('y el API recibe su area, no una lista de responsables', async () => {
    listTickets.mockResolvedValue(respuesta());
    await load(evento('', { rol: 'USER', email: 'tecnico@x.test' }));
    const params = listTickets.mock.lastCall[1];
    expect(params.get('area')).toBe('soporte_tecnico');
    expect(params.has('assigned_to')).toBe(false);
    expect(params.get('incluir_mios')).toBe('1');
  });
});

describe('"Sin área asignada" elegida', () => {
  it('no se le pide al servidor: se recorta sobre la pagina, como siempre', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = await load(evento('?area=__sin_area__'));
    expect(listTickets.mock.lastCall[1].has('area')).toBe(false);
    expect(ids(data)).toEqual(['suelto']);
  });
});

describe('"Todas las áreas"', () => {
  //  19/10/2026: la pantalla solo mostraba un area a la vez, y en produccion
  //  ningun ticket abierto trae el area escrita. Quien administra pidio ver
  //  "todos los tickets sin importar el area".
  it('quien administra ve la cola entera, y al API no le pide area', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('?area=__todas__')));
    const params = listTickets.mock.lastCall[1];
    expect(params.has('area')).toBe(false);
    expect(params.has('area_responsables')).toBe(false);
    expect(params.has('incluir_mios')).toBe(false);
    expect(ids(data).sort()).toEqual(TODOS.map((t) => t.id).sort());
    expect(data.todasLasAreas.etiqueta).toBe('Todas las áreas');
  });

  it('la tarjeta del inicio lleva los totales del servidor, no la suma de tarjetas', async () => {
    listTickets.mockResolvedValue({
      ...respuesta(),
      totals: { count: 6, open: 6, urgent: 2, awaiting_reply: 5, shown: 6 }
    });
    const data = /** @type {any} */ (await load(evento('')));
    expect(data.todasLasAreas).toMatchObject({
      total: 6, urgentes: 2, sin_respuesta: 5, sin_asignar: 1
    });
  });

  it('un colaborador que la pide por la URL cae en su area, y no ve la tarjeta', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('?area=__todas__', { rol: 'USER', email: 'tecnico@x.test' })));
    expect(listTickets.mock.lastCall[1].get('area')).toBe('soporte_tecnico');
    //  'ventas' es SUYO, y desde el 20/10/2026 lo ve (lo suyo siempre). Lo
    //  que no ve es lo de otra area que no le toca.
    expect(ids(data)).not.toContain('viejo-cartera');
    expect(data.todasLasAreas).toBeNull();
  });

  it('dentro de un area concreta no manda totales de "todas"', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('?area=cartera')));
    expect(data.todasLasAreas).toBeNull();
  });
});

describe('la cola nueva (23/10/2026)', () => {
  //  27/10/2026, pedido del usuario: «los ticket no tienen que salir fuera de
  //  la tarjeta». La pantalla abre en las tarjetas, sin area elegida; la cola
  //  aparece al elegir una. Hasta ese dia abria directo en «Todas las áreas».
  it('quien administra abre en las tarjetas, sin un area elegida', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('')));
    expect(data.areaElegida).toBe('');
    expect(data.tarjetas[0]).toMatchObject({ nombre: data.todas, etiqueta: 'Todas las áreas' });
  });

  it('la tarjeta «Todas las áreas» abre la cola entera', async () => {
    listTickets.mockResolvedValue(respuesta());
    const todas = /** @type {any} */ (await load(evento(''))).todas;
    const data = /** @type {any} */ (await load(evento(`?area=${encodeURIComponent(todas)}`)));
    expect(data.areaElegida).toBe(todas);
    expect(ids(data).sort()).toEqual(TODOS.map((t) => t.id).sort());
  });

  it('un supervisor ve la cola entera como quien administra, con selector', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('', { rol: 'SUPERVISOR', email: 'admin@x.test' })));
    expect(data.areaElegida).toBe('');
    expect(data.soloMiArea).toBe(false);
    expect(data.reparte).toBe(true);
    expect(data.selectorAreas.length).toBeGreaterThan(1);
  });

  it('un colaborador abre en la tarjeta de su area, y no tiene selector', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('', { rol: 'USER', email: 'tecnico@x.test' })));
    expect(data.areaElegida).toBe('');
    expect(data.tarjetas.map((/** @type {any} */ a) => a.nombre)).toEqual(['soporte_tecnico']);
    expect(data.selectorAreas).toEqual([]);
  });

  it('"Míos" y "Sin asignar" se le piden al servidor, y el numero de la pestaña es el suyo', async () => {
    listTickets.mockResolvedValue({
      ...respuesta([SUELTO_SIN_NADA]),
      totals: { count: 1, open: 6, urgent: 0, awaiting_reply: 0, shown: 1, mine: 2, unassigned: 1 }
    });
    const data = /** @type {any} */ (await load(evento('?vista=sin_asignar')));
    expect(listTickets.mock.lastCall[1].get('vista')).toBe('sin_asignar');
    expect(data.conteosVista).toEqual({ mios: 2, sin_asignar: 1 });
    // La pagina NO se vuelve a filtrar en el navegador: lo que mando el API es lo que hay.
    expect(ids(data)).toEqual(['suelto']);
  });

  it('el orden por defecto es "vence primero"; "Más recientes" se pide por la URL', async () => {
    listTickets.mockResolvedValue(respuesta());
    await load(evento(''));
    expect(listTickets.mock.lastCall[1].get('ordering')).toBe('vence');
    await load(evento('?orden=recientes'));
    expect(listTickets.mock.lastCall[1].get('ordering')).toBe('-created_at');
  });

  it('dentro de un area, el selector cuenta todas las areas con una consulta sin filtro de area', async () => {
    listTickets.mockReset();
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('?area=cartera')));
    expect(listTickets).toHaveBeenCalledTimes(2);
    const global = listTickets.mock.calls[0][1];
    expect(global.has('area')).toBe(false);
    expect(global.get('limit')).toBe('1');
    expect(listTickets.mock.lastCall[1].get('area')).toBe('cartera');
    const soporte = data.selectorAreas.find((a) => a.nombre === 'soporte_tecnico');
    expect(soporte.total).toBe(3);
  });
});

describe('las tarjetas por area vuelven (27/10/2026)', () => {
  it('quien administra ve "Todas las áreas" y una tarjeta por area, con sus numeros', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('')));
    const [todas, ...areas] = data.tarjetas;
    expect(todas).toMatchObject({ nombre: data.todas, etiqueta: 'Todas las áreas', todas: true });
    expect(todas.total).toBe(data.totals.open);
    expect(areas.map((a) => a.nombre)).toEqual(data.selectorAreas.slice(1).map((a) => a.nombre));
    for (const a of areas) {
      expect(a).toHaveProperty('urgentes');
      expect(a).toHaveProperty('sin_respuesta');
      expect(a).toHaveProperty('sin_asignar');
    }
  });

  it('dentro de un area, las demas tarjetas siguen con los numeros de la cola entera', async () => {
    listTickets.mockReset();
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('?area=cartera')));
    const soporte = data.tarjetas.find((a) => a.nombre === 'soporte_tecnico');
    //  La misma cuenta que el selector, que sale de la consulta sin filtro.
    expect(soporte.total).toBe(data.selectorAreas.find((a) => a.nombre === 'soporte_tecnico').total);
    expect(soporte.total).toBeGreaterThan(0);
  });

  it('un colaborador ve solo la tarjeta de su area', async () => {
    listTickets.mockResolvedValue(respuesta());
    const data = /** @type {any} */ (await load(evento('', { rol: 'USER', email: 'tecnico@x.test' })));
    expect(data.tarjetas.map((a) => a.nombre)).toEqual(['soporte_tecnico']);
  });
});

describe('"Asignarme"', () => {
  /** @param {string} rol */
  function pedido(rol) {
    const fd = new FormData();
    fd.set('id', 'caso-1');
    return /** @type {any} */ ({
      request: { formData: async () => fd },
      cookies: { get: () => 'token' },
      locals: { profile: { role: rol }, user: { email: 'admin@x.test' } }
    });
  }

  /** @param {number} status */
  const rechazo = (status) => Object.assign(new Error('x'), { status, body: {} });

  it('toma el ticket por /tomar/, sin decidir el rol aca (24/10/2026)', async () => {
    //  Un colaborador tambien llega al backend: es quien decide si el ticket
    //  es de su area. Antes esta accion le cortaba el paso por rol.
    for (const rol of ['ADMIN', 'SUPERVISOR', 'USER']) {
      tomarTicket.mockReset();
      tomarTicket.mockResolvedValue({});
      const r = await actions.asignarme(pedido(rol));
      expect(r).toEqual({ asignado: 'caso-1' });
      expect(tomarTicket.mock.lastCall[1]).toBe('caso-1');
    }
  });

  it('si otra persona lo tomo primero, lo dice', async () => {
    tomarTicket.mockReset();
    tomarTicket.mockRejectedValue(rechazo(409));
    const r = /** @type {any} */ (await actions.asignarme(pedido('USER')));
    expect(r.status).toBe(409);
    expect(r.data.error).toMatch(/primero/);
  });

  it('si no es de su area, lo dice y no lo disfraza de error generico', async () => {
    tomarTicket.mockReset();
    tomarTicket.mockRejectedValue(rechazo(403));
    const r = /** @type {any} */ (await actions.asignarme(pedido('USER')));
    expect(r.status).toBe(403);
    expect(r.data.error).toMatch(/área/);
  });
});
