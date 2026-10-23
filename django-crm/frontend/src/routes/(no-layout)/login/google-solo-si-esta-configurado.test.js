/**
 * EL LOGIN OFRECE GOOGLE SOLO SI GOOGLE ESTA CONFIGURADO.
 *
 * Medido en produccion el 23/10/2026: el enlace del boton llevaba
 * client_id=undefined (GOOGLE_CLIENT_ID no esta definido), y ese era el boton
 * PRINCIPAL de la pantalla. Se afirma sobre lo que devuelve `load`, que es lo
 * que decide si la pantalla dibuja el boton.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const entorno = vi.hoisted(() => ({ env: {} }));
vi.mock('$env/dynamic/private', () => entorno);

const { load } = await import('./+page.server.js');

/**
 * Lo minimo que `load` lee de un evento: la URL y las cookies.
 * @returns {any}
 */
function evento() {
  const guardadas = new Map();
  return {
    guardadas,
    url: new URL('https://dexter.example/login'),
    cookies: {
      get: () => undefined,
      set: (nombre, valor) => guardadas.set(nombre, valor),
      delete: (nombre) => guardadas.delete(nombre)
    }
  };
}

describe('Google en el login', () => {
  beforeEach(() => {
    entorno.env = {};
  });

  it('sin GOOGLE_CLIENT_ID no hay boton ni cookies de PKCE', async () => {
    const e = evento();
    const datos = /** @type {any} */ (await load(e));
    expect(datos.google_url).toBeNull();
    expect(e.guardadas.has('oauth_state')).toBe(false);
    expect(e.guardadas.has('oauth_code_verifier')).toBe(false);
  });

  it('con GOOGLE_CLIENT_ID el enlace lleva ese client_id, nunca "undefined"', async () => {
    entorno.env = { GOOGLE_CLIENT_ID: 'cliente-de-prueba', GOOGLE_LOGIN_DOMAIN: 'https://dexter.example' };
    const e = evento();
    const datos = /** @type {any} */ (await load(e));
    const url = new URL(datos.google_url);
    expect(url.searchParams.get('client_id')).toBe('cliente-de-prueba');
    expect(datos.google_url).not.toContain('undefined');
    expect(e.guardadas.has('oauth_state')).toBe(true);
  });
});
