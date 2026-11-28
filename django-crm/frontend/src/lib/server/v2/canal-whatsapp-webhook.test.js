import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La URL que el administrador de un ISP pega en Meta (31/10/2026).
 *
 * Antes la pantalla le pedía "Tu dominio" para armarla. Con el motor publicado
 * bajo el dominio de Dexter, ese dominio no es del ISP: es de la plataforma, el
 * mismo para todas las empresas, y el administrador no tiene cómo saberlo. Así
 * que viene de la instalación (`PRIVATE_WEBHOOK_BASE_URL`) y la pantalla la
 * muestra entera, lista para copiar.
 */
const { envMock } = vi.hoisted(() => ({
  /** @type {Record<string, string>} */
  envMock: {}
}));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { urlDelWebhook } = await import('./canal-whatsapp.js');

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
});

describe('urlDelWebhook', () => {
  it('arma la URL de la empresa con el dominio de la instalación', () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = 'https://wa.dexter.co';
    expect(urlDelWebhook('rapilink')).toBe('https://wa.dexter.co/canales/whatsapp/rapilink');
  });

  it('cada empresa recibe la suya con el mismo dominio', () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = 'https://wa.dexter.co';
    expect(urlDelWebhook('otra-isp')).toBe('https://wa.dexter.co/canales/whatsapp/otra-isp');
  });

  it('tolera el dominio sin esquema, con barra final o con espacios', () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = '  wa.dexter.co/ ';
    expect(urlDelWebhook('rapilink')).toBe('https://wa.dexter.co/canales/whatsapp/rapilink');
  });

  it('Meta exige https: un http se sube a https', () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = 'http://wa.dexter.co';
    expect(urlDelWebhook('rapilink')).toBe('https://wa.dexter.co/canales/whatsapp/rapilink');
  });

  it('sin la variable devuelve vacío: la pantalla vuelve a pedir el dominio', () => {
    expect(urlDelWebhook('rapilink')).toBe('');
  });

  it('sin empresa devuelve vacío: una URL sin slug no atiende a nadie', () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = 'https://wa.dexter.co';
    expect(urlDelWebhook('')).toBe('');
    expect(urlDelWebhook(undefined)).toBe('');
  });

  it('el slug va codificado en la ruta', () => {
    envMock.PRIVATE_WEBHOOK_BASE_URL = 'https://wa.dexter.co';
    expect(urlDelWebhook('a b')).toBe('https://wa.dexter.co/canales/whatsapp/a%20b');
  });
});
