import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Ninguna empresa recibe el tenant de otra.
 *
 * Lo que se afirma es el EFECTO —qué devuelve— y no que la función exista. La
 * propiedad que importa es negativa: ante la duda, **nada**. Un default acá no
 * se vería como un error, se vería como una pantalla con datos; los de otra
 * empresa.
 */
const { envMock } = vi.hoisted(() => ({
  /** @type {Record<string, string>} */
  envMock: {}
}));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));

const { tenantDeLaSesion, destinoDelAsistente, olvidarTenantsRecordados, TENANT_RECORDADO_MS } =
  await import('./tenant.js');

const CONFIGURADO = {
  PRIVATE_ASISTENTE_URL: 'http://motor:5000',
  PRIVATE_ASISTENTE_TENANT: 'rapilink'
};

/** @param {any} respuesta */
function fetchQueDevuelve(respuesta) {
  return vi.fn().mockResolvedValue(respuesta);
}

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
  Object.assign(envMock, CONFIGURADO);
  // El módulo recuerda la empresa de cada organización entre requests
  // (11/11/2026); las pruebas comparten el módulo, así que cada una arranca
  // sin recuerdos.
  olvidarTenantsRecordados();
});

describe('una pregunta por empresa cada tanto, no una por request (11/11/2026)', () => {
  it('EL EFECTO: el segundo request de la misma organización no vuelve al motor', async () => {
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
    expect(await tenantDeLaSesion({ org: { id: 'org-1' } }, fetch)).toBe('rapilink');
    const otroRequest = /** @type {any} */ ({ org: { id: 'org-1' } });
    expect(await tenantDeLaSesion(otroRequest, fetch)).toBe('rapilink');
    expect(fetch).toHaveBeenCalledTimes(1);
    // Y lo deja en los locals del nuevo request, como si lo hubiera preguntado.
    expect(otroRequest.tenant).toBe('rapilink');
  });

  it('cada organización se recuerda por separado', async () => {
    const fetch = vi.fn(async (/** @type {string} */ url) => ({
      ok: true,
      json: async () => ({ tenant: url.endsWith('/org-1') ? 'rapilink' : 'otra' })
    }));
    expect(await tenantDeLaSesion({ org: { id: 'org-1' } }, fetch)).toBe('rapilink');
    expect(await tenantDeLaSesion({ org: { id: 'org-2' } }, fetch)).toBe('otra');
    expect(await tenantDeLaSesion({ org: { id: 'org-1' } }, fetch)).toBe('rapilink');
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('un null NO se recuerda: la empresa recién configurada no espera a que venza nada', async () => {
    const sinAsistente = fetchQueDevuelve({ ok: false, status: 404, json: async () => ({}) });
    expect(await tenantDeLaSesion({ org: { id: 'org-nueva' } }, sinAsistente)).toBeNull();
    const yaConfigurada = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'nueva' }) });
    expect(await tenantDeLaSesion({ org: { id: 'org-nueva' } }, yaConfigurada)).toBe('nueva');
    expect(yaConfigurada).toHaveBeenCalledTimes(1);
  });

  it('lo recordado vence', async () => {
    vi.useFakeTimers();
    try {
      const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
      await tenantDeLaSesion({ org: { id: 'org-1' } }, fetch);
      vi.advanceTimersByTime(TENANT_RECORDADO_MS + 1);
      await tenantDeLaSesion({ org: { id: 'org-1' } }, fetch);
      expect(fetch).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('de qué empresa son los datos de quien inició sesión', () => {
  it('resuelve el tenant preguntándole al motor por la organización', async () => {
    const fetch = fetchQueDevuelve({
      ok: true,
      json: async () => ({ tenant: 'rapilink' })
    });
    const locals = { org: { id: 'org-1' } };

    expect(await tenantDeLaSesion(locals, fetch)).toBe('rapilink');
    expect(fetch.mock.calls[0][0]).toContain('/tenant-de-organizacion/org-1');
  });

  it('cada organización recibe el suyo, no el de la anterior', async () => {
    const primera = await tenantDeLaSesion(
      { org: { id: 'org-A' } },
      fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'primera' }) })
    );
    const segunda = await tenantDeLaSesion(
      { org: { id: 'org-B' } },
      fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'segunda' }) })
    );

    expect(primera).toBe('primera');
    expect(segunda).toBe('segunda');
  });

  it('sin sesión no hay tenant, y NO cae a la variable de entorno', async () => {
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'x' }) });

    // La variable existe y vale 'rapilink'. Aun así, sin organización la
    // respuesta es nada: caer a ella sería reintroducir el problema entero.
    expect(await tenantDeLaSesion({}, fetch)).toBeNull();
    expect(await tenantDeLaSesion(null, fetch)).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('una empresa sin asistente configurado no recibe ninguno', async () => {
    // 404 es una respuesta legítima del motor, no una falla.
    const fetch = fetchQueDevuelve({ ok: false, status: 404, json: async () => ({}) });
    expect(await tenantDeLaSesion({ org: { id: 'org-sin' } }, fetch)).toBeNull();
  });

  it('el motor caído tampoco habilita servir los datos de otra empresa', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    expect(await tenantDeLaSesion({ org: { id: 'org-1' } }, fetch)).toBeNull();
  });

  it('no vuelve a preguntar dentro del mismo request', async () => {
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
    const locals = { org: { id: 'org-1' } };

    await tenantDeLaSesion(locals, fetch);
    await tenantDeLaSesion(locals, fetch);

    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('la empresa no vuelve a salir del entorno', () => {
  /**
   * Guarda de arquitectura, hermana de `tests/test_nucleo_sin_tenants.py`.
   *
   * Hasta el 24/09/2026 `PRIVATE_ASISTENTE_TENANT` se leía en 70 archivos: la
   * instalación entera servía a una sola empresa, y con dos cada una de esas
   * lecturas le habría servido a un ISP los datos del otro (PRD §8.13).
   *
   * Afirma sobre el EFECTO —que nadie lee esa variable— y no sobre que exista
   * `tenantDeLaSesion`. Una prueba de que el mecanismo existe no prueba que se
   * use, y acá lo que importa es que NO se use el otro. Antes hubo un puente
   * (`tenantDeLaInstalacion`) que devolvía la variable a la vista; se borró
   * cuando el último archivo dejó de necesitarlo, y esto impide que vuelva.
   *
   * Si esta prueba falla: la empresa se resuelve con `tenantDeLaSesion(locals,
   * fetch)`. Si `locals` no llega hasta ahí, hay que pasarlo — no leer el
   * entorno.
   */
  it('ningún archivo de src/ lee PRIVATE_ASISTENTE_TENANT', async () => {
    const { readdirSync, readFileSync } = await import('node:fs');
    const { join, sep: SEP } = await import('node:path');

    const raiz = join(process.cwd(), 'src');
    /** @type {string[]} */
    const culpables = [];

    /** @param {string} dir */
    function recorrer(dir) {
      for (const entrada of readdirSync(dir, { withFileTypes: true })) {
        const ruta = join(dir, entrada.name);
        if (entrada.isDirectory()) {
          recorrer(ruta);
          continue;
        }
        // Los .test.js quedan fuera: ahí la variable aparece dentro de los
        // mocks del entorno, que es legítimo — es justo lo que simulan.
        if (!entrada.name.endsWith('.js') && !entrada.name.endsWith('.svelte')) continue;
        if (entrada.name.endsWith('.test.js')) continue;
        if (readFileSync(ruta, 'utf8').includes('env.PRIVATE_ASISTENTE_TENANT')) {
          culpables.push(ruta.slice(raiz.length + 1).split(SEP).join('/'));
        }
      }
    }
    recorrer(raiz);

    expect(culpables).toEqual([]);
    // 30 s y no los 5 por defecto: recorrer src/ entero cuesta ~8 s cuando el
    // proyecto esta montado desde Windows dentro del contenedor. Es el precio
    // de una guarda que mira el arbol de verdad en vez de confiar en un
    // import, y se paga una vez por corrida.
  }, 30_000);
});

describe('el destino, que reemplaza ocho copias idénticas', () => {
  it('devuelve base y tenant cuando los dos existen', async () => {
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
    const d = await destinoDelAsistente({ org: { id: 'org-1' } }, fetch);
    expect(d).toEqual({ baseUrl: 'http://motor:5000', tenant: 'rapilink' });
  });

  it('sin sesión no hay destino, aunque la variable de entorno exista', async () => {
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'x' }) });
    expect(await destinoDelAsistente({}, fetch)).toBeNull();
  });

  it('sin URL del motor tampoco, y ni siquiera pregunta por el tenant', async () => {
    delete envMock.PRIVATE_ASISTENTE_URL;
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'x' }) });
    expect(await destinoDelAsistente({ org: { id: 'org-1' } }, fetch)).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('una sola pregunta al motor por request (04/11/2026)', () => {
  it('EL EFECTO: nueve lecturas en paralelo hacen UNA llamada, y todas reciben el tenant', async () => {
    // El hub de Configuración dispara nueve lecturas del motor a la vez; cada
    // una pasa por acá ANTES de que la primera haya guardado `locals.tenant`.
    // Nueve llamadas iguales contra un motor de 8 hilos era parte de
    // "Configuración demora o no muestra nada".
    const locals = /** @type {any} */ ({ org: { id: 'org-1' } });
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
    const nueve = await Promise.all(Array.from({ length: 9 }, () => tenantDeLaSesion(locals, fetch)));
    expect(nueve).toEqual(Array(9).fill('rapilink'));
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('y la que llega después tampoco vuelve a preguntar', async () => {
    const locals = /** @type {any} */ ({ org: { id: 'org-1' } });
    const fetch = fetchQueDevuelve({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
    await tenantDeLaSesion(locals, fetch);
    await tenantDeLaSesion(locals, fetch);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('dos requests distintos (dos `locals`) NO comparten la respuesta', async () => {
    // La memoria es por request, nunca global: es la garantía de que una
    // empresa no recibe el tenant de la anterior.
    const a = /** @type {any} */ ({ org: { id: 'org-a' } });
    const b = /** @type {any} */ ({ org: { id: 'org-b' } });
    const fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tenant: 'primera' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tenant: 'segunda' }) });
    expect(await tenantDeLaSesion(a, fetch)).toBe('primera');
    expect(await tenantDeLaSesion(b, fetch)).toBe('segunda');
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('un motor que no contesta: null dentro del plazo, no una espera infinita', async () => {
    vi.useFakeTimers();
    try {
      const locals = /** @type {any} */ ({ org: { id: 'org-1' } });
      // fetch respeta la señal: rechaza cuando el plazo la aborta.
      const fetch = vi.fn((_url, { signal }) => new Promise((_, rechazar) => {
        signal.addEventListener('abort', () => rechazar(signal.reason));
      }));
      const pendiente = tenantDeLaSesion(locals, fetch);
      await vi.advanceTimersByTimeAsync(3100);
      expect(await pendiente).toBeNull();
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(fetch.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
    } finally {
      vi.useRealTimers();
    }
  });

  it('tras un fallo, el siguiente llamado del mismo request vuelve a intentar', async () => {
    // El "en vuelo" se limpia al terminar: un fallo no deja pegada una promesa
    // resuelta en null para el resto del request.
    const locals = /** @type {any} */ ({ org: { id: 'org-1' } });
    const fetch = vi.fn()
      .mockRejectedValueOnce(new Error('caído'))
      .mockResolvedValueOnce({ ok: true, json: async () => ({ tenant: 'rapilink' }) });
    expect(await tenantDeLaSesion(locals, fetch)).toBeNull();
    expect(await tenantDeLaSesion(locals, fetch)).toBe('rapilink');
  });
});
