import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * LA CADENA DE DESPACHO, DEL BACKEND A LA PANTALLA.
 *
 * Por qué esta prueba existe y no alcanza ninguna del backend. CLAUDE.md §6 lo
 * dice con dos cicatrices del 29/09/2026: `requiere_noc` viajaba bien desde el
 * backend --con su prueba pasando-- y la capa servidor del frontend lo dejaba
 * caer, así que la bandeja del NOC quedaba vacía para siempre; y la línea de
 * tiempo leía `estado_nuevo` mientras el backend escribe `nuevo_estado`, con la
 * prueba en verde porque FABRICABA el evento con la clave equivocada.
 *
 * Las dos fallas viven en el MISMO salto que esta pantalla: el backend
 * responde `snake_case`, esta capa renombra a `camelCase`, y un renombre que
 * se pierde no da error --da una pantalla que dice algo falso con total
 * aplomo--. `despacho.js` y `cuadrillas.js` --el circuito entero del ticket a
 * la cuadrilla-- no tenían ninguna. (Medido: 38 de los 63 módulos de
 * `lib/server/v2/` no tienen prueba, así que esto no es una excepción; lo que
 * hace a estos dos distintos es que ya se cobraron dos defectos.)
 *
 * QUÉ SE AFIRMA: el EFECTO sobre los datos que llegan a la pantalla, con la
 * forma EXACTA que devuelve el backend --no una inventada--. Por eso cada
 * constante de abajo apunta a la línea que la produce: si el backend renombra
 * un campo, esta prueba se pone roja del lado correcto.
 *
 * LO QUE NO CUBRE, y hay que decirlo: no compila el `.svelte`, así que no ve
 * qué dibuja la pantalla con estos datos (el techo del harness está explicado
 * en `vitest.config.js`). Cubre hasta `load`, que es donde se perdieron los
 * dos campos de la historia.
 */

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load, actions } = await import('./+page.server.js');

/* ------------------------------------------------------------------ *
 *  LA FORMA REAL DEL BACKEND
 * ------------------------------------------------------------------ */

/** `campo/despacho_pantalla_views.py::PlantillasDeTrabajoView` -> Response({...}) */
const PLANTILLAS = {
  plantillas: [
    { id: 'wtv-1', nombre: 'Correctivo FTTH', labor: 'correctivo', requisitos: 3 },
    { id: 'wtv-2', nombre: 'Instalación nueva', labor: '', requisitos: 5 }
  ],
  labores: [{ id: 'correctivo', texto: 'Correctivo' }],
  sin_clasificar: 1
};

/** `campo/despacho_pantalla_views.py::CasosDespachablesView` -> Response({...}) */
const CASOS = {
  casos: [
    {
      id: 'caso-1',
      nombre: 'Sin internet desde ayer',
      estado: 'Open',
      prioridad: 'High',
      creado: '2026-10-13T10:00:00+00:00',
      servicio: '6580',
      ticket: '90354',
      orden_activa: null,
      sugerencia: { work_type_version_id: 'wtv-1', motivo: 'fibra' },
      localidad: 'CANDELARIA 2'
    }
  ],
  tope: 25,
  sin_aprobados: false
};

/**
 * `campo/cuadrillas_views.py::RepartoView.get` -> Response({...}), PLANA.
 *
 * Dos cosas de esta forma no son decorativas y la primera versión de esta
 * prueba se equivocó en las dos:
 *
 *  1. La respuesta NO viene envuelta en `{propuesta: ...}`. `proponerReparto`
 *     devuelve `{propuesta: d}` donde `d` es la respuesta entera, así que
 *     envolverla acá da `propuesta.propuesta` y todos los conteos leen 0 --que
 *     es justo el falso verde que esta prueba tiene que no producir--.
 *
 *  2. **`labor` vive en la ASIGNACIÓN, no en la orden.** `_orden_json`
 *     (`cuadrillas_views.py:1086`) devuelve exactamente estas seis claves y
 *     ninguna más. Poner `labor` dentro de cada orden haría pasar un
 *     `conteosDel` roto.
 */
const ORDEN = {
  id: 'o-1',
  numero: 1001,
  cliente: 'CARLOS DIAZ',
  direccion: 'CL 12 # 3-45',
  zona: 'CANDELARIA 2',
  prioridad: 'High'
};
const orden = (id, numero) => ({ ...ORDEN, id, numero });

const PROPUESTA = {
  fecha: '2026-10-13',
  asignaciones: [
    {
      jornada: 'jo-1',
      cuadrilla: { id: 'cu-1', nombre: 'Cuadrilla 1' },
      labor: 'correctivo',
      zonas: ['CANDELARIA 2'],
      integrantes: 2,
      ordenes: [orden('o-1', 1001), orden('o-2', 1002)]
    },
    {
      jornada: 'jo-2',
      cuadrilla: { id: 'cu-2', nombre: 'Cuadrilla 2' },
      labor: 'instalacion',
      zonas: ['EL CARMEN'],
      integrantes: 3,
      ordenes: [orden('o-3', 1003)]
    }
  ],
  sin_zona: [orden('o-4', 1004)],
  sin_cuadrilla: [orden('o-5', 1005), orden('o-6', 1006)],
  sobrantes: [orden('o-7', 1007)],
  sin_clasificar: [orden('o-8', 1008), orden('o-9', 1009), orden('o-10', 1010)]
};

/** Responde según el endpoint, como lo haría el backend de verdad. */
function backendSano() {
  apiRequest.mockImplementation(async (endpoint) => {
    if (endpoint.startsWith('/campo/plantillas-de-trabajo/')) return PLANTILLAS;
    if (endpoint.startsWith('/campo/casos-despachables/')) return CASOS;
    if (endpoint.includes('reparto')) return PROPUESTA;
    throw new Error(`endpoint sin doble en la prueba: ${endpoint}`);
  });
}

const CTX = /** @type {any} */ ({
  cookies: { get: () => 'token' },
  url: new URL('http://x/supervisor-noc/despacho')
});

beforeEach(() => {
  apiRequest.mockReset();
  backendSano();
});

/* ------------------------------------------------------------------ *
 *  NINGÚN CAMPO SE PIERDE EN EL CAMINO
 * ------------------------------------------------------------------ */

describe('load: lo que el backend manda llega a la pantalla', () => {
  it('no deja caer ninguna de las tres respuestas', async () => {
    const d = await load(CTX);

    //  Plantillas: el aviso de «sin clasificar» es el que decide si quien
    //  despacha sabe que esa plantilla NO la va a repartir el reparto.
    expect(d.plantillas).toHaveLength(2);
    expect(d.labores).toHaveLength(1);
    expect(d.plantillasSinClasificar).toBe(1);

    //  Casos: `localidad` es lo que precarga el barrio, y sin barrio la orden
    //  queda en `sin_zona` para siempre.
    expect(d.casos).toHaveLength(1);
    expect(d.casos[0].localidad).toBe('CANDELARIA 2');
    expect(d.casos[0].sugerencia?.work_type_version_id).toBe('wtv-1');
    expect(d.casos[0].orden_activa).toBeNull();
    expect(d.tope).toBe(25);

    expect(d.error).toBe(false);
    expect(d.repartoError).toBeNull();
  });

  it('cada clave de cada caso sobrevive, no solo las que alguien recordó', async () => {
    const d = await load(CTX);
    //  Afirmar campo por campo deja pasar el que nadie listó. El backend arma
    //  la fila completa en un solo dict: se compara ese dict.
    expect(Object.keys(d.casos[0]).sort()).toEqual(Object.keys(CASOS.casos[0]).sort());
  });

  it('cuenta las cinco salidas del reparto, y las cuatro que NO entraron', async () => {
    const d = await load(CTX);

    expect(d.conteos.ordenes).toBe(3);
    expect(d.conteos.cuadrillas).toBe(2);

    //  LAS CUATRO QUE NO ENTRARON. Se leen de `propuesta.sin_*`, y si el
    //  backend renombrara una, `?? []` la dejaría en 0 SIN ERROR: la pantalla
    //  diría «no quedó nada afuera» con tres órdenes sin clasificar.
    expect(d.conteos.sinZona).toBe(1);
    expect(d.conteos.sinCuadrilla).toBe(2);
    expect(d.conteos.sobrantes).toBe(1);
    expect(d.conteos.sinClasificar).toBe(3);

    //  Y el desglose por labor, que es lo que una persona mira para saber
    //  cuántos técnicos van a cada cosa.
    const porLabor = Object.fromEntries(d.conteos.porLabor.map((x) => [x.labor, x]));
    expect(porLabor.correctivo).toEqual({ labor: 'correctivo', ordenes: 2, cuadrillas: 1 });
    expect(porLabor.instalacion).toEqual({ labor: 'instalacion', ordenes: 1, cuadrillas: 1 });
  });

  it('una jornada sin labor declarada se nombra, no se descarta', async () => {
    apiRequest.mockImplementation(async (endpoint) => {
      if (endpoint.includes('reparto')) {
        return {
          ...PROPUESTA,
          asignaciones: [
            { jornada: 'jo-1', cuadrilla: { id: 'cu-1' }, labor: null,
              ordenes: [orden('o-1', 1001)] }
          ]
        };
      }
      return endpoint.startsWith('/campo/plantillas') ? PLANTILLAS : CASOS;
    });

    const d = await load(CTX);
    //  Se nombra, no desaparece: una cuadrilla que salió sin decir a qué sale
    //  es una anomalía que hay que ver, no un hueco en el total.
    expect(d.conteos.ordenes).toBe(1);
    expect(d.conteos.porLabor[0].labor).toBe('sin clasificar');
  });

  it('la labor NO se lee de la orden: _orden_json no la trae', async () => {
    //  LA MUTACIÓN QUE ESTA PRUEBA EXISTE PARA MATAR. `conteosDel` leía
    //  `o.labor` de cada orden y `_orden_json` nunca la manda, así que el
    //  panel decía «N cuadrillas a sin clasificar» SIEMPRE --con todo el
    //  backend en verde--. Si alguien vuelve a leerla de la orden, acá se
    //  pone rojo: estas órdenes no tienen `labor` y la asignación sí.
    const d = await load(CTX);
    for (const a of PROPUESTA.asignaciones) {
      for (const o of a.ordenes) expect(o.labor).toBeUndefined();
    }
    expect(d.conteos.porLabor.map((x) => x.labor).sort())
      .toEqual(['correctivo', 'instalacion']);
    expect(d.conteos.porLabor.some((x) => x.labor === 'sin clasificar')).toBe(false);
  });
});

/* ------------------------------------------------------------------ *
 *  «VACÍO» Y «NO SE PUDO LEER» NO SE DIBUJAN IGUAL
 * ------------------------------------------------------------------ */

describe('load: distingue nadie-aprobó-nada de no-se-pudo-leer', () => {
  it('sin_aprobados viaja, y no se confunde con un error', async () => {
    apiRequest.mockImplementation(async (endpoint) => {
      if (endpoint.startsWith('/campo/plantillas')) return PLANTILLAS;
      if (endpoint.startsWith('/campo/casos')) return { casos: [], tope: 25, sin_aprobados: true };
      return PROPUESTA;
    });

    const d = await load(CTX);
    expect(d.sinAprobados).toBe(true);
    //  Esto es lo que separa «el Supervisor todavía no aprobó nada» --que dice
    //  qué hacer-- de «la consulta falló» --que dice que algo está roto--.
    expect(d.error).toBe(false);
  });

  it('una lectura que falla NO se disfraza de lista vacía', async () => {
    apiRequest.mockImplementation(async (endpoint) => {
      if (endpoint.startsWith('/campo/casos')) throw new Error('502');
      if (endpoint.startsWith('/campo/plantillas')) return PLANTILLAS;
      return PROPUESTA;
    });

    const d = await load(CTX);
    expect(d.error).toBe(true);
    expect(d.casos).toEqual([]);
    expect(d.sinAprobados).toBe(false);
  });

  it('si el reparto no se puede calcular, la pantalla sigue sirviendo', async () => {
    apiRequest.mockImplementation(async (endpoint) => {
      if (endpoint.includes('reparto')) throw new Error('el motor no responde');
      return endpoint.startsWith('/campo/plantillas') ? PLANTILLAS : CASOS;
    });

    const d = await load(CTX);
    //  Despachar no depende de que la propuesta se pueda calcular: si cayera
    //  todo, nadie podría mandar el caso urgente a campo.
    expect(d.casos).toHaveLength(1);
    expect(d.repartoError).toBeTruthy();
    expect(d.conteos).toBeNull();
  });
});

/* ------------------------------------------------------------------ *
 *  DESPACHAR: LO QUE DE VERDAD SALE EN EL CUERPO
 * ------------------------------------------------------------------ */

/** Un submit del formulario de la pantalla, con los `name=` que tiene. */
function submit(campos) {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({ request: { formData: async () => f }, cookies: CTX.cookies });
}

const DESPACHO_OK = {
  case_id: 'caso-1',
  work_type_version_id: 'wtv-1',
  zona: 'CANDELARIA 2',
  prioridad: 'High',
  programada_para: '2026-10-14'
};

describe('despachar', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ orden: { numero: 1042 } });
  });

  it('la zona llega al backend: sin ella la orden queda en sin_zona para siempre', async () => {
    const r = await actions.despachar(submit(DESPACHO_OK));

    const [endpoint, opciones] = apiRequest.mock.calls[0];
    expect(endpoint).toBe('/campo/trabajos/crear/');
    expect(opciones.method).toBe('POST');
    //  El campo que ya falló una vez. El formulario lo precarga de
    //  `caso.localidad` y lo marca `required`; acá se afirma que ADEMÁS sale.
    expect(opciones.body.zona).toBe('CANDELARIA 2');
    expect(opciones.body.case_id).toBe('caso-1');
    expect(opciones.body.work_type_version_id).toBe('wtv-1');
    expect(r.numero).toBe(1042);
  });

  it('si el caso YA tenía una orden abierta, la confirmación lo dice', async () => {
    //  `CrearOrdenView` devuelve `ordenes_activas_del_caso` --las que existían
    //  ANTES de esta-- y el comentario del backend nombra a su consumidor:
    //  «Que la UI pueda avisar "este caso ya tiene una orden activa"». No lo
    //  usaba nadie: la confirmación decía «Orden #1042 despachada.» y punto.
    apiRequest.mockResolvedValue({
      orden: { numero: 1042 },
      ordenes_activas_del_caso: [988, 1001],
      server_time: '2026-10-13T20:00:00+00:00'
    });

    const r = await actions.despachar(submit(DESPACHO_OK));
    expect(r.hecho).toContain('Orden #1042 despachada.');
    expect(r.hecho).toContain('2 órdenes abiertas');
    expect(r.hecho).toContain('#988');
    expect(r.hecho).toContain('#1001');
  });

  it('una sola se dice en singular', async () => {
    apiRequest.mockResolvedValue({
      orden: { numero: 1042 }, ordenes_activas_del_caso: [988]
    });
    const r = await actions.despachar(submit(DESPACHO_OK));
    expect(r.hecho).toContain('una orden abierta');
    expect(r.hecho).toContain('#988');
  });

  it('la orden que se acaba de crear NO se cuenta como «ya había»', async () => {
    //  `activas` se calcula antes del create, pero si alguna vez incluyera la
    //  nueva, el mensaje diria que ya habia una orden siendo que es esta.
    apiRequest.mockResolvedValue({
      orden: { numero: 1042 }, ordenes_activas_del_caso: [1042]
    });
    const r = await actions.despachar(submit(DESPACHO_OK));
    //  NO se fija el texto entero: el mensaje tambien dice a quien quedo
    //  asignada, y eso lo decide otra parte que puede cambiar su redaccion sin
    //  que este caso tenga nada que opinar. Lo que se afirma es la AUSENCIA
    //  del aviso, que es de lo que trata esta prueba.
    expect(r.hecho).toContain('Orden #1042 despachada');
    expect(r.hecho).not.toContain('ya tenía');
    expect(r.hecho).not.toContain('#1042)');
  });

  it('sin órdenes previas la confirmación no agrega ruido', async () => {
    apiRequest.mockResolvedValue({
      orden: { numero: 1042 }, ordenes_activas_del_caso: []
    });
    const r = await actions.despachar(submit(DESPACHO_OK));
    expect(r.hecho).toContain('Orden #1042 despachada');
    expect(r.hecho).not.toContain('Atención');
  });

  it('un campo vacío viaja como ausente, no como cadena vacía', async () => {
    await actions.despachar(submit({ ...DESPACHO_OK, zona: '', prioridad: '' }));
    const [, opciones] = apiRequest.mock.calls[0];
    //  `''` y `undefined` no son lo mismo para el serializer: una cadena vacía
    //  puede pasar una validación de «requerido» y dejar el dato en blanco.
    expect(opciones.body.zona).toBeUndefined();
    expect(opciones.body.prioridad).toBeUndefined();
  });

  it('el mismo despacho repetido lleva la MISMA clave de idempotencia', async () => {
    await actions.despachar(submit(DESPACHO_OK));
    await actions.despachar(submit(DESPACHO_OK));

    const clave1 = apiRequest.mock.calls[0][1].headers['Idempotency-Key'];
    const clave2 = apiRequest.mock.calls[1][1].headers['Idempotency-Key'];
    //  Una clave nueva por intento es un identificador único, NO una clave
    //  idempotente: con eso, un doble clic crea dos órdenes (CLAUDE.md §12).
    expect(clave2).toBe(clave1);
    expect(clave1).toContain('caso-1');
  });

  it('otra plantilla u otra fecha es otro despacho, y lleva otra clave', async () => {
    await actions.despachar(submit(DESPACHO_OK));
    await actions.despachar(submit({ ...DESPACHO_OK, work_type_version_id: 'wtv-2' }));
    await actions.despachar(submit({ ...DESPACHO_OK, programada_para: '2026-10-20' }));

    const claves = apiRequest.mock.calls.map((c) => c[1].headers['Idempotency-Key']);
    //  Si no cambiara, una segunda visita deliberada al mismo caso se
    //  silenciaría como si fuera un doble clic.
    expect(new Set(claves).size).toBe(3);
  });

  it('sin plantilla no sale ninguna llamada', async () => {
    const r = await actions.despachar(submit({ ...DESPACHO_OK, work_type_version_id: '' }));
    expect(r.status).toBe(400);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('el motivo del backend se muestra, no se reemplaza por una frase propia', async () => {
    //  LA FORMA REAL del error: `apiRequest` lanza un Error con `.status` y
    //  `.body` (`$lib/api-helpers.js:135`). NO pone `.data` -- y leer `.data`
    //  era justo el defecto: la persona veía `NO_SE_PUDO_CREAR`.
    apiRequest.mockRejectedValue(
      Object.assign(new Error('NO_SE_PUDO_CREAR'),
                    { status: 400, body: { error: 'NO_SE_PUDO_CREAR',
                                           detalle: 'Esa plantilla es un borrador.' } })
    );
    const r = await actions.despachar(submit(DESPACHO_OK));
    expect(r.status).toBe(400);
    expect(r.data.error).toBe('Esa plantilla es un borrador.');
  });

  it('con el código Y la frase, se muestra LA FRASE', async () => {
    //  El backend de campo manda las dos: `error` es para una máquina,
    //  `detalle` para una persona. Mostrar el código teniendo la frase es
    //  elegir el peor de los dos.
    apiRequest.mockRejectedValue(
      Object.assign(new Error('YA_PROGRAMADA'),
                    { status: 409, body: { error: 'YA_PROGRAMADA',
                                           detalle: 'Ya hay una orden abierta para este caso.' } })
    );
    const r = await actions.despachar(submit(DESPACHO_OK));
    expect(r.data.error).toBe('Ya hay una orden abierta para este caso.');
    expect(r.data.error).not.toContain('YA_PROGRAMADA');
  });
});

/* ------------------------------------------------------------------ *
 *  HACER QUE EL SUPERVISOR MIRE AHORA
 * ------------------------------------------------------------------ */

describe('ciclo', () => {
  const conRol = (role) => /** @type {any} */ ({
    cookies: CTX.cookies,
    locals: { profile: { role } }
  });

  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('solo los roles de gestión lo pueden despertar', async () => {
    const r = await actions.ciclo(conRol('AGENT'));
    expect(r.status).toBe(403);
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('un ADMIN sí, y el número de propuestas llega al mensaje', async () => {
    apiRequest.mockResolvedValue({ resumen: { propuestas_nuevas: 2 } });
    const r = await actions.ciclo(conRol('ADMIN'));
    expect(r.hecho).toContain('2 propuestas');
  });

  it('una sola propuesta se dice en singular', async () => {
    apiRequest.mockResolvedValue({ resumen: { propuestas_nuevas: 1 } });
    const r = await actions.ciclo(conRol('SUPERVISOR'));
    expect(r.hecho).toContain('1 propuesta');
    expect(r.hecho).not.toContain('propuestas');
  });

  it('sin número no se inventa un cero', async () => {
    apiRequest.mockResolvedValue({});
    const r = await actions.ciclo(conRol('OPERACIONES'));
    //  «Dejó 0 propuestas» sería una afirmación que nadie midió: el motor no
    //  dijo cuántas, no dijo que no hubiera ninguna.
    expect(r.hecho).not.toContain('0');
  });
});

/* ------------------------------------------------------------------ *
 *  EL DÍA ES EL DE LA EMPRESA (27/10/2026)
 * ------------------------------------------------------------------ */

describe('load: el día del reparto en el reloj de la empresa', () => {
  it('a las 20:30 de Bogotá pide el reparto de hoy, no el de mañana', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    //  Lunes 26 a las 20:30 de Bogotá = martes 27 a la 01:30 UTC.
    vi.setSystemTime(new Date('2026-10-27T01:30:00Z'));
    try {
      const sano = apiRequest.getMockImplementation();
      apiRequest.mockImplementation(async (endpoint, ...resto) =>
        endpoint === '/org/settings/' ? { timezone: 'America/Bogota' } : sano?.(endpoint, ...resto)
      );

      const d = /** @type {any} */ (
        await load({ ...CTX, locals: { org: { id: 'org-del-dia' } } })
      );

      expect(d.dia).toBe('2026-10-26');
      const reparto = apiRequest.mock.calls.map(([e]) => e).find((e) => e.includes('reparto'));
      expect(reparto).toContain('fecha=2026-10-26');
    } finally {
      vi.useRealTimers();
    }
  });
});
