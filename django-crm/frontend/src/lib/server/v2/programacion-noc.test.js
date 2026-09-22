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
  CAUSAS
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
