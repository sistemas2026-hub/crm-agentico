import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const {
  listarPropuestas,
  leerPropuesta,
  leerIndicadores,
  correrCiclo,
  correrAsistente,
  revisarPropuesta,
  cancelarPropuesta,
  leerAutonomia,
  resumenOperativo,
  traducirError
} = await import('$lib/server/v2/supervisor-noc.js');

const event = /** @type {any} */ ({ cookies: { get: () => 'token' } });

/** Un error con forma de los que arroja `apiRequest`. */
const http = (/** @type {number} */ status) => Object.assign(new Error('x'), { status });

beforeEach(() => {
  apiRequest.mockReset();
});

describe('listarPropuestas', () => {
  it('devuelve las propuestas y su total tal como los manda el backend', async () => {
    apiRequest.mockResolvedValue({
      count: 92,
      resultados: [{ id: 'a', tipo_senal: 'caso_abierto_antiguo' }]
    });

    const r = await listarPropuestas(event);

    expect(r.count).toBe(92);
    expect(r.resultados).toHaveLength(1);
    expect(r.error).toBeNull();
    expect(apiRequest).toHaveBeenCalledWith('/operaciones/propuestas/', {}, { cookies: event.cookies });
  });

  it('reenvia el filtro por tipo de senal sin alterarlo', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [] });

    await listarPropuestas(event, { tipo_senal: 'caso_desincronizado' });

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/propuestas/?tipo_senal=caso_desincronizado');
  });

  it('ante un fallo deja el total en null, NO en 0', async () => {
    // Un 0 diria "no hay propuestas". Lo cierto es "no se pudo saber", y son
    // afirmaciones distintas.
    apiRequest.mockRejectedValue(http(500));

    const r = await listarPropuestas(event);

    expect(r.count).toBeNull();
    expect(r.resultados).toEqual([]);
    expect(r.error?.codigo).toBe('ERROR_SERVIDOR');
  });

  it('un 403 se distingue de una falla: es el permiso funcionando', async () => {
    apiRequest.mockRejectedValue(http(403));

    const r = await listarPropuestas(event);

    expect(r.error?.codigo).toBe('SIN_PERMISO');
    expect(r.error?.mensaje).toContain('Jefe de Operaciones');
  });

  it('una respuesta vacia del backend no rompe la pantalla', async () => {
    apiRequest.mockResolvedValue({});

    const r = await listarPropuestas(event);

    expect(r.count).toBe(0);
    expect(r.resultados).toEqual([]);
    expect(r.error).toBeNull();
  });
});

describe('leerPropuesta', () => {
  it('pide el detalle por id', async () => {
    apiRequest.mockResolvedValue({ id: 'abc', evidencia: [] });

    const r = await leerPropuesta(event, 'abc');

    expect(apiRequest.mock.calls[0][0]).toBe('/operaciones/propuestas/abc/');
    expect(r.datos.id).toBe('abc');
  });

  it('un 404 se traduce sin filtrar si el id existe o es de otra organizacion', async () => {
    apiRequest.mockRejectedValue(http(404));

    const r = await leerPropuesta(event, 'abc');

    expect(r.datos).toBeNull();
    expect(r.error?.codigo).toBe('NO_ENCONTRADA');
  });
});

describe('correrCiclo', () => {
  it('hace UN solo POST, sin reintentos', async () => {
    apiRequest.mockResolvedValue({ resumen: { senales: 3 }, shadow_mode: true, acciones_ejecutadas: 0 });

    await correrCiclo(event);

    expect(apiRequest).toHaveBeenCalledTimes(1);
    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/operaciones/supervisor/ciclo/');
    expect(opciones.method).toBe('POST');
  });

  it('propaga el fallo en vez de reintentar por su cuenta', async () => {
    apiRequest.mockRejectedValue(http(500));

    await expect(correrCiclo(event)).rejects.toThrow();
    expect(apiRequest).toHaveBeenCalledTimes(1);
  });
});

describe('revisar y cancelar', () => {
  it('revisar manda la decision y el comentario al endpoint del backend', async () => {
    apiRequest.mockResolvedValue({ ejecutada: false, aviso: 'Ninguna acción se ejecutó.' });

    const r = await revisarPropuesta(event, 'abc', { decision: 'aceptada', comentario: '' });

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/operaciones/propuestas/abc/revisar/');
    expect(opciones.method).toBe('POST');
    expect(opciones.body.decision).toBe('aceptada');
    // La garantia que esta pantalla no puede erosionar.
    expect(r.ejecutada).toBe(false);
  });

  it('cancelar usa su propia ruta y manda el motivo', async () => {
    apiRequest.mockResolvedValue({ propuesta: {}, ejecutada: false });

    await cancelarPropuesta(event, 'abc', 'la orden ya se programó');

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/operaciones/propuestas/abc/cancelar/');
    expect(opciones.body).toEqual({ motivo: 'la orden ya se programó' });
  });

  it('el asistente manda el dominio en el cuerpo, no en la ruta', async () => {
    apiRequest.mockResolvedValue({ recomendaciones: [] });

    await correrAsistente(event, 'programacion');

    const [ruta, opciones] = apiRequest.mock.calls[0];
    expect(ruta).toBe('/operaciones/asistentes/');
    expect(opciones.body).toEqual({ dominio: 'programacion' });
  });
});

describe('no se llama a ningun sistema externo', () => {
  it('ninguna funcion del modulo pega contra WispHub, SmartOLT ni una ruta de ejecucion', async () => {
    apiRequest.mockResolvedValue({ count: 0, resultados: [] });

    await listarPropuestas(event);
    await leerPropuesta(event, 'abc');
    await leerIndicadores(event);
    await correrCiclo(event);
    await correrAsistente(event, 'compromiso');
    await revisarPropuesta(event, 'abc', { decision: 'aceptada' });
    await cancelarPropuesta(event, 'abc', 'motivo');

    const rutas = apiRequest.mock.calls.map((c) => String(c[0]));
    expect(rutas.every((r) => r.startsWith('/operaciones/'))).toBe(true);
    for (const prohibido of ['wisphub', 'smartolt', 'acciones_propuestas', 'ejecucion_autonoma', 'ejecutar']) {
      expect(rutas.some((r) => r.toLowerCase().includes(prohibido))).toBe(false);
    }
  });

  it('leerAutonomia es de LECTURA: sin motor configurado no inventa un estado', async () => {
    const r = await leerAutonomia();

    // Lo que NO puede pasar: decir "DETENIDA" sin haberlo leido. Esa es la
    // falla ABIERTA que el interruptor existe para evitar.
    expect(r.estado).toBeNull();
    expect(r.permitido).toBeNull();
    expect(r.motivo).toContain('no está configurado');
  });
});

describe('resumenOperativo: cero y "sin datos" no son lo mismo', () => {
  const arbol = (/** @type {any} */ vivas) => ({
    supervisor: {
      senales_vigentes: { estado: 'VALIDO', valor: 7, cobertura: 1 },
      senales_por_tipo: vivas
    }
  });

  it('sin arbol de indicadores, TODAS las tarjetas dicen SIN_DATO', async () => {
    const r = resumenOperativo(null);

    expect(r).toHaveLength(5);
    expect(r.every((k) => k.dato.estado === 'SIN_DATO')).toBe(true);
    expect(r.every((k) => k.dato.valor === null)).toBe(true);
  });

  it('con arbol, un tipo ausente es un CERO real', async () => {
    // 'senales_por_tipo' solo trae las señales con al menos una ocurrencia,
    // asi que la ausencia de la clave -- habiendo arbol -- significa cero.
    const r = resumenOperativo(arbol({}));

    const bloqueos = r.find((k) => k.clave === 'bloqueos');
    expect(bloqueos?.dato.estado).toBe('VALIDO');
    expect(bloqueos?.dato.valor).toBe(0);
  });

  it('un tipo presente se muestra con el valor que dio el backend', async () => {
    const r = resumenOperativo(
      arbol({ incidencia_sin_resolver: { estado: 'VALIDO', valor: 4, cobertura: 1 } })
    );

    expect(r.find((k) => k.clave === 'incidencias')?.dato.valor).toBe(4);
  });

  it('la suma de dos tipos no se calcula si falta alguno', async () => {
    const r = resumenOperativo(null);

    expect(r.find((k) => k.clave === 'vencimientos')?.dato.estado).toBe('SIN_DATO');
  });

  it('no inventa un delta contra ayer: no hay serie historica que lo sostenga', async () => {
    const r = resumenOperativo(arbol({}));

    for (const k of r) {
      expect(k.dato).not.toHaveProperty('delta');
      expect(k.dato).not.toHaveProperty('vs_ayer');
    }
  });
});

describe('traducirError', () => {
  it('cada status tiene su mensaje, y ninguno expone el error crudo', () => {
    const casos = /** @type {const} */ ([
      [401, 'NO_AUTENTICADO'],
      [403, 'SIN_PERMISO'],
      [404, 'NO_ENCONTRADA'],
      [409, 'YA_REVISADA'],
      [500, 'ERROR_SERVIDOR'],
      [503, 'ERROR_SERVIDOR']
    ]);

    for (const [status, codigo] of casos) {
      const e = traducirError(http(status), 'las propuestas');
      expect(e.codigo).toBe(codigo);
      expect(e.mensaje).not.toContain('Error:');
      expect(e.mensaje).not.toContain('at ');
    }
  });

  it('un fallo de red (sin status) se distingue de un error del servidor', () => {
    const e = traducirError(new Error('fetch failed'), 'las propuestas');

    expect(e.codigo).toBe('SIN_RESPUESTA');
    expect(e.mensaje).toContain('no respondió');
  });
});
