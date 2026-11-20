import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La cadena de la URL del webhook (31/10/2026), sin sustituir el módulo del
 * canal: el motor (simulado en `fetch`) contesta con el slug de la empresa de
 * la sesión, y lo que tiene que salir de `load` es la URL entera con el dominio
 * de la instalación. Es el salto donde el slug podría caerse con el resto en
 * verde: `urlDelWebhook` tiene su prueba, pero nada dice que alguien le pase
 * el slug que devolvió el motor.
 */
const { envMock } = vi.hoisted(() => ({
  /** @type {Record<string, string>} */
  envMock: {}
}));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { load } = await import('./+page.server.js');

/** @param {string} slug */
function motorQueContesta(slug) {
  return vi.fn(async (/** @type {string} */ url) => {
    if (url.includes('/configuracion/canales?')) {
      return new Response(JSON.stringify({ whatsapp: { tenant_slug: slug, activo: false } }));
    }
    return new Response(JSON.stringify({ secretos: [] }));
  });
}

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
  envMock.PRIVATE_ASISTENTE_URL = 'http://motor:5000';
});

describe('load de /settings/canales/whatsapp', () => {
  it('entrega la URL de la empresa de la sesión con el dominio de la instalación', async () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = 'wa.dexter.co';
    const datos = await load(
      /** @type {any} */ ({ fetch: motorQueContesta('otra-isp'), locals: { tenant: 'otra-isp' } })
    );
    expect(datos.url_webhook).toBe('https://wa.dexter.co/canales/whatsapp/otra-isp');
  });

  it('sin dominio declarado entrega vacío y la pantalla lo pide a mano', async () => {
    const datos = await load(
      /** @type {any} */ ({ fetch: motorQueContesta('otra-isp'), locals: { tenant: 'otra-isp' } })
    );
    expect(datos.url_webhook).toBe('');
  });
});
