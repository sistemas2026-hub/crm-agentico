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

const { tenantDeLaSesion, destinoDelAsistente } =
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
