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
  SENALES_PROGRAMACION
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
