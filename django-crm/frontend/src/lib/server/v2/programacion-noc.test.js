import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const {
  leerJornada,
  leerCapacidad,
  secuenciarJornada,
  publicarProgramacion,
  resumenProgramacion,
  SENALES_PROGRAMACION,
  leerOrden,
  leerCargaPersona,
  reprogramarOrden,
  cambiarSecuencia,
  CAUSAS,
  listarPlanes,
  programarOrden,
  planesQueCubren,
  leerMaterialesDeOrden,
  leerSeguimientoDeOrden,
  registrarSeguimiento,
  leerBloqueosAbiertos,
  resolverBloqueo
} = await import('$lib/server/v2/programacion-noc.js');

const event = /** @type {any} */ ({ cookies: { get: () => 'token' } });
const http = (/** @type {number} */ status) => Object.assign(new Error('x'), { status });

beforeEach(() => apiRequest.mockReset());

describe('leerJornada', () => {
  it('siempre manda el dia: el backend responde 400 sin filtro', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [], resumen: null });

    await leerJornada(event, '2026-09-22');

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/programacion/jornada/?dia=2026-09-22');
  });

  it('devuelve lineas y resumen tal como los manda el backend', async () => {
    apiRequest.mockResolvedValue({
      count: 2,
      resultados: [{ id: '1', secuencia: 0 }, { id: '2', secuencia: 3 }],
      resumen: { secuencia_cero: 1, secuencias_empatadas: 0, lineas_en_empate: 0 }
    });

    const r = await leerJornada(event, '2026-09-22');

    expect(r.count).toBe(2);
    expect(r.lineas).toHaveLength(2);
    expect(r.resumen.secuencia_cero).toBe(1);
    expect(r.error).toBeNull();
  });

  it('ante un fallo el total queda en null, no en 0', async () => {
    apiRequest.mockImplementationOnce(() => Promise.reject(http(500)));

    const r = await leerJornada(event, '2026-09-22');

    expect(r.count).toBeNull();
    expect(r.error?.codigo).toBe('ERROR_SERVIDOR');
  });
});

describe('leerCapacidad', () => {
  it('pide la capacidad del dia y no la recalcula', async () => {
    apiRequest.mockResolvedValue({
      jornada: { minutos: 480 },
      resultados: [{ profile: { id: 'p1' }, jornada: { minutos: 480 }, carga: { minutos_conocidos: 240 } }]
    });

    const r = await leerCapacidad(event, '2026-09-22');

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/capacidad/jornada/?dia=2026-09-22');
    // La capacidad viaja como vino: no se deriva de nuevo en esta capa.
    expect(r.personas[0].carga.minutos_conocidos).toBe(240);
  });
});

describe('escrituras: solo orden propuesto y estado de plan', () => {
  it('secuenciar usa su ruta y manda el dia', async () => {
    apiRequest.mockResolvedValue({});

    await secuenciarJornada(event, { dia: '2026-09-22' });

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/operaciones/programacion/jornada/secuenciar/');
    expect(opciones.method).toBe('POST');
    expect(opciones.body).toEqual({ dia: '2026-09-22' });
  });

  it('publicar apunta al plan por id', async () => {
    apiRequest.mockResolvedValue({});

    await publicarProgramacion(event, 'plan-1');

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/programacion/plan-1/publicar/');
  });

  it('ninguna ruta del modulo toca un sistema externo ni despacha', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [] });

    await leerJornada(event, '2026-09-22');
    await leerCapacidad(event, '2026-09-22');
    await secuenciarJornada(event, { dia: '2026-09-22' });
    await publicarProgramacion(event, 'plan-1');

    const rutas = apiRequest.mock.calls.map((c) => String(c[0]));
    expect(rutas.every((r) => r.startsWith('/operaciones/'))).toBe(true);
    for (const prohibido of ['wisphub', 'smartolt', 'despach', 'ejecucion_autonoma', 'asignar']) {
      expect(rutas.some((r) => r.toLowerCase().includes(prohibido))).toBe(false);
    }
  });
});

describe('resumenProgramacion', () => {
  const jornadaOk = (/** @type {any[]} */ lineas) => ({ lineas, count: lineas.length, error: null });
  const capVacia = { personas: [], error: null };

  it('cuenta como SIN SECUENCIAR las lineas con secuencia 0', async () => {
    // El backend decidio (E-2) que 0 significa sin secuenciar, no "primera".
    const r = resumenProgramacion(
      jornadaOk([{ secuencia: 0 }, { secuencia: 0 }, { secuencia: 5 }]),
      capVacia
    );

    expect(r.find((k) => k.clave === 'sin_secuenciar')?.dato.valor).toBe(2);
  });

  it('sin jornada, las tarjetas que dependen de ella dicen SIN_DATO', async () => {
    const r = resumenProgramacion({ lineas: [], count: null, error: { mensaje: 'x' } }, capVacia);

    expect(r.find((k) => k.clave === 'ordenes')?.dato.estado).toBe('SIN_DATO');
    expect(r.find((k) => k.clave === 'sin_secuenciar')?.dato.estado).toBe('SIN_DATO');
  });

  it('la ocupacion se marca parcial si a alguien le faltan duraciones', async () => {
    const r = resumenProgramacion(jornadaOk([]), {
      error: null,
      personas: [
        { jornada: { minutos: 480 }, carga: { minutos_conocidos: 240 }, faltantes: [{ orden: 'x' }] }
      ]
    });

    const oc = r.find((k) => k.clave === 'ocupacion');
    expect(oc?.dato.valor).toBe(50);
    expect(oc?.dato.estado).toBe('DATOS_INSUFICIENTES');
    expect(oc?.dato.motivo).toContain('sobre lo conocido');
  });

  it('sin capacidad, la ocupacion dice SIN_DATO en vez de 0%', async () => {
    const r = resumenProgramacion(jornadaOk([]), { personas: [], error: { mensaje: 'x' } });

    const oc = r.find((k) => k.clave === 'ocupacion');
    expect(oc?.dato.estado).toBe('SIN_DATO');
    expect(oc?.dato.valor).toBeNull();
  });

  it('con todas las duraciones, la ocupacion es VALIDO', async () => {
    const r = resumenProgramacion(jornadaOk([]), {
      error: null,
      personas: [{ jornada: { minutos: 480 }, carga: { minutos_conocidos: 480 }, faltantes: [] }]
    });

    const oc = r.find((k) => k.clave === 'ocupacion');
    expect(oc?.dato.estado).toBe('VALIDO');
    expect(oc?.dato.valor).toBe(100);
  });
});

describe('senales del dominio', () => {
  it('son las de programacion, y ninguna de casos o incidencias', () => {
    expect(SENALES_PROGRAMACION).toContain('orden_sin_programar');
    expect(SENALES_PROGRAMACION).toContain('programacion_sin_publicar');
    expect(SENALES_PROGRAMACION).not.toContain('caso_abierto_antiguo');
    expect(SENALES_PROGRAMACION).not.toContain('incidencia_sin_resolver');
  });
});

describe('acciones nuevas sobre M03', () => {
  it('leerOrden descarta telefono y GPS del cliente', async () => {
    apiRequest.mockResolvedValue({
      id: 'o1',
      numero: 1035,
      cliente: {
        nombre: 'Cliente Prueba',
        direccion: 'Calle 45 #12-30',
        telefono: '3113683499',
        lat: 4.65,
        lng: -74.05
      },
      evidencias: [{ id: 'e1' }, { id: 'e2' }]
    });

    const r = await leerOrden(event, 'o1');

    // Lo que SI hace falta para programar una visita.
    expect(r.datos.cliente.nombre).toBe('Cliente Prueba');
    expect(r.datos.cliente.direccion).toBe('Calle 45 #12-30');
    // Lo que no, y no viaja al navegador: se recorta en el servidor.
    expect(r.datos.cliente).not.toHaveProperty('telefono');
    expect(r.datos.cliente).not.toHaveProperty('lat');
    expect(r.datos.cliente).not.toHaveProperty('lng');
    // El objeto entero tampoco los lleva por otro camino.
    expect(JSON.stringify(r.datos)).not.toContain('3113683499');
    expect(JSON.stringify(r.datos)).not.toContain('74.05');
    // Las evidencias se cuentan, no se vuelcan.
    expect(r.datos.n_evidencias).toBe(2);
  });

  it('reprogramar manda el plan que vino de la linea, no uno inventado', async () => {
    apiRequest.mockResolvedValue({});

    await reprogramarOrden(event, 'o1', {
      programacion_semanal_id: 'plan-7',
      programada_para: '2026-09-23T14:00',
      causa: 'reprogramacion',
      motivo: 'lluvia'
    });

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/campo/trabajos/o1/reprogramar/');
    expect(opciones.body.programacion_semanal_id).toBe('plan-7');
    expect(opciones.body.causa).toBe('reprogramacion');
  });

  it('cambiar secuencia manda SOLO secuencia, causa y motivo', async () => {
    apiRequest.mockResolvedValue({});

    await cambiarSecuencia(event, 'linea-1', { secuencia: 3, causa: 'cambio_de_prioridad', motivo: '' });

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/operaciones/programacion/linea/linea-1/secuencia/');
    // Cambiar el orden NO es reprogramar: nada de fecha, plan, zona ni prioridad.
    for (const prohibido of ['programada_para', 'dia', 'plan', 'zona', 'prioridad']) {
      expect(opciones.body).not.toHaveProperty(prohibido);
    }
    expect(opciones.body.secuencia).toBe(3);
  });

  it('leerCargaPersona acota al dia y a la persona', async () => {
    apiRequest.mockResolvedValue({ profile: { id: 'p1' } });

    await leerCargaPersona(event, '2026-09-22', 'p1');

    expect(apiRequest.mock.calls[0][0]).toBe(
      '/operaciones/capacidad/jornada/?dia=2026-09-22&profile_id=p1'
    );
  });

  it('las causas son las del catalogo cerrado del backend', () => {
    const valores = CAUSAS.map((c) => c.valor);
    for (const v of valores) {
      expect([
        'ausencia',
        'bloqueo',
        'falta_material',
        'dependencia',
        'reprogramacion',
        'cambio_de_prioridad',
        'dato_incompleto',
        'demora_sin_causa_registrada'
      ]).toContain(v);
    }
  });

  it('ninguna de las acciones nuevas toca un sistema externo', async () => {
    apiRequest.mockResolvedValue({ cliente: {} });

    await leerOrden(event, 'o1');
    await leerCargaPersona(event, '2026-09-22', 'p1');
    await reprogramarOrden(event, 'o1', { programacion_semanal_id: 'p', programada_para: 'x' });
    await cambiarSecuencia(event, 'l1', { secuencia: 0 });

    const rutas = apiRequest.mock.calls.map((c) => String(c[0]));
    expect(rutas.every((r) => r.startsWith('/operaciones/') || r.startsWith('/campo/'))).toBe(true);
    for (const prohibido of ['wisphub', 'smartolt', 'despach', 'ejecucion_autonoma']) {
      expect(rutas.some((r) => r.toLowerCase().includes(prohibido))).toBe(false);
    }
  });
});

describe('planes semanales', () => {
  const plan = (/** @type {any} */ x) => ({
    id: 'p1',
    semana_inicio: '2026-09-21',
    semana_fin: '2026-09-27',
    estado: 'borrador',
    estado_display: 'Borrador',
    admite_lineas: true,
    ...x
  });

  it('1. carga los planes y usa el filtro del backend, no uno propio', async () => {
    apiRequest.mockResolvedValue({ count: 2, resultados: [plan({}), plan({ id: 'p2' })] });

    const r = await listarPlanes(event);

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/programacion/?admite_lineas=1');
    expect(r.planes).toHaveLength(2);
    expect(r.error).toBeNull();
  });

  it('puede pedirlos todos cuando se lo piden explicitamente', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [] });

    await listarPlanes(event, false);

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/programacion/');
  });

  it('2. filtra por la semana que cubre el dia, con los campos del backend', () => {
    const dentro = plan({ id: 'dentro' });
    const fuera = plan({ id: 'fuera', semana_inicio: '2026-09-28', semana_fin: '2026-10-04' });

    const r = planesQueCubren([dentro, fuera], '2026-09-23');

    expect(r.map((p) => p.id)).toEqual(['dentro']);
  });

  it('un plan sin semana declarada no se descarta en silencio', () => {
    const raro = { id: 'raro', estado: 'borrador' };

    expect(planesQueCubren([raro], '2026-09-23').map((p) => p.id)).toEqual(['raro']);
  });

  it('5. lista vacia: count 0 y sin error -- no hay planes es un dato, no una falla', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [] });

    const r = await listarPlanes(event);

    expect(r.count).toBe(0);
    expect(r.planes).toEqual([]);
    expect(r.error).toBeNull();
  });

  it('6. un 404 dice que falta la RUTA, no que falten planes', async () => {
    // La distincion importa: "no hay planes" manda a crear uno; "la ruta no
    // responde" manda a mirar el despliegue.
    apiRequest.mockImplementationOnce(() => Promise.reject(http(404)));

    const r = await listarPlanes(event);

    expect(r.error?.codigo).toBe('RUTA_AUSENTE');
    expect(r.error?.mensaje).toContain('no está disponible en este entorno');
    expect(r.count).toBeNull();
  });

  it('6b. otros errores se traducen sin exponer el crudo', async () => {
    apiRequest.mockImplementationOnce(() => Promise.reject(http(500)));

    const r = await listarPlanes(event);

    expect(r.error?.codigo).toBe('ERROR_SERVIDOR');
    expect(r.count).toBeNull();
  });

  it('4. programar manda el plan elegido como programacion_semanal_id', async () => {
    apiRequest.mockResolvedValue({});

    await programarOrden(event, 'orden-9', {
      programacion_semanal_id: 'p1',
      programada_para: '2026-09-23T08:00',
      causa: 'reprogramacion',
      motivo: ''
    });

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/campo/trabajos/orden-9/programar/');
    expect(opciones.method).toBe('POST');
    expect(opciones.body.programacion_semanal_id).toBe('p1');
    expect(opciones.body.programada_para).toBe('2026-09-23T08:00');
  });

  it('programar no manda campos que el serializer no declara', async () => {
    apiRequest.mockResolvedValue({});

    await programarOrden(event, 'orden-9', {
      programacion_semanal_id: 'p1',
      programada_para: '2026-09-23T08:00'
    });

    const cuerpo = apiRequest.mock.calls[0][1].body;
    // 'org' sale de la sesion: un 'organization_id' en el cuerpo no tiene
    // donde aterrizar, y el backend directamente no lo declara.
    for (const prohibido of ['org', 'organization_id', 'estado']) {
      expect(cuerpo).not.toHaveProperty(prohibido);
    }
  });

  it('listar planes no ejecuta ninguna escritura', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [] });

    await listarPlanes(event);

    expect(apiRequest.mock.calls[0][1]).toEqual({});
  });
});


describe('el seguimiento de campo', () => {
  it('manda requiere_noc y detener al backend', async () => {
    // LA GUARDA DEL DEFECTO REAL: esta capa no reenviaba esos dos campos, asi que
    // todo bloqueo entraba como "no es del NOC" y esa bandeja quedaba vacia para
    // siempre. El backend los respetaba y tenia prueba; el dato se perdia ANTES de
    // llegarle. Una prueba de backend no podia verlo.
    apiRequest.mockResolvedValue({ id: 'x', tipo: 'bloqueo_campo' });

    await registrarSeguimiento(event, 'o1', {
      momento: 'bloqueo',
      respuestas: { motivo: 'sin acceso' },
      requiereNoc: true,
      detener: true
    });

    const cuerpo = apiRequest.mock.calls[0][1].body;
    expect(cuerpo.requiere_noc).toBe(true);
    expect(cuerpo.detener).toBe(true);
    // Y las respuestas del formulario siguen viajando aparte: `requiere_noc` es
    // dato de plataforma, no un campo del esquema del ISP.
    expect(cuerpo.respuestas).toEqual({ motivo: 'sin acceso' });
  });

  it('no inventa requiere_noc cuando nadie lo mando', async () => {
    apiRequest.mockResolvedValue({ id: 'x' });

    await registrarSeguimiento(event, 'o1', {
      momento: 'avance',
      respuestas: { nota: 'sigo' }
    });

    const cuerpo = apiRequest.mock.calls[0][1].body;
    expect('requiere_noc' in cuerpo).toBe(false);
    expect('detener' in cuerpo).toBe(false);
  });

  it('el body va como objeto: apiRequest es el que serializa', async () => {
    // Pasarlo ya en texto lo enviaria como un string JSON dentro de otro, y el
    // backend leeria un cuerpo vacio.
    apiRequest.mockResolvedValue({ id: 'x' });
    await registrarSeguimiento(event, 'o1', { momento: 'avance', respuestas: {} });
    expect(typeof apiRequest.mock.calls[0][1].body).toBe('object');
  });

  it('un 422 devuelve el motivo del backend y los errores por campo', async () => {
    // `traducirError` es el traductor de las LECTURAS y su texto generico
    // ("no fue posible consultar...") taparia justo el dato util.
    // `mockImplementationOnce` y no `mockRejectedValue`: el segundo crea la
    // promesa rechazada al configurar el mock y queda sin consumir, asi que el
    // runner la reporta como fallo del test aunque el codigo la maneje bien. Es el
    // patron que ya usa el resto de este archivo.
    apiRequest.mockImplementationOnce(() =>
      Promise.reject(
        Object.assign(new Error('x'), {
          status: 422,
          body: { detalle: 'Falta el nivel inicial.', campos: { nivel: 'requerido' } }
        })
      )
    );

    const { error } = await registrarSeguimiento(event, 'o1', {
      momento: 'inicio',
      respuestas: {}
    });

    expect(error.mensaje).toBe('Falta el nivel inicial.');
    expect(error.campos).toEqual({ nivel: 'requerido' });
  });
});

describe('los bloqueos', () => {
  it('bloqueados y requiere NOC son dos consultas distintas', async () => {
    apiRequest.mockResolvedValue({ bloqueos: [], total: 0 });

    await leerBloqueosAbiertos(event);
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/bloqueos/');

    apiRequest.mockClear();
    await leerBloqueosAbiertos(event, { soloNoc: true });
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/bloqueos/?requiere_noc=1');
  });

  it('resolver no manda volver_a cuando nadie eligio otro destino', async () => {
    // El estado al que vuelve lo guardo el bloqueo al abrirse: mandar un destino
    // por defecto desde el frontend seria adivinarlo.
    apiRequest.mockResolvedValue({ volvio_a: 'en_sitio' });

    await resolverBloqueo(event, 'o1', { queSeHizo: 'se gestiono', rol: 'noc' });

    const cuerpo = apiRequest.mock.calls[0][1].body;
    expect('volver_a' in cuerpo).toBe(false);
    expect(cuerpo.que_se_hizo).toBe('se gestiono');
    expect(cuerpo.resuelto_por_rol).toBe('noc');
  });

  it('un 409 dice que alguien lo resolvio antes', async () => {
    apiRequest.mockImplementationOnce(() =>
      Promise.reject(Object.assign(new Error('x'), { status: 409, body: {} }))
    );
    const { error } = await resolverBloqueo(event, 'o1', { queSeHizo: 'algo' });
    expect(error.codigo).toBe('SIN_BLOQUEO_ABIERTO');
  });
});

describe('los materiales de la orden', () => {
  it('la custodia del tecnico no se pide si no se la piden', async () => {
    // El kit del dia es de la PERSONA, no del trabajo.
    apiRequest.mockResolvedValue({ consumido: [] });

    await leerMaterialesDeOrden(event, 'o1');
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o1/materiales/');

    apiRequest.mockClear();
    await leerMaterialesDeOrden(event, 'o1', { custodia: true });
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o1/materiales/?custodia=1');
  });

  it('la bitacora se lee de su propia ruta', async () => {
    apiRequest.mockResolvedValue({ eventos: [] });
    await leerSeguimientoDeOrden(event, 'o1');
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/trabajos/o1/seguimiento/');
  });
});
