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

const { tenantDeLaSesion, tenantDeLaInstalacion } = await import('./tenant.js');

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

describe('el puente que se borra cuando termine la migración', () => {
  it('devuelve la variable de entorno, a la vista de quien la use', () => {
    expect(tenantDeLaInstalacion()).toBe('rapilink');
  });

  it('y nada si no está definida', () => {
    delete envMock.PRIVATE_ASISTENTE_TENANT;
    expect(tenantDeLaInstalacion()).toBeNull();
  });
});
