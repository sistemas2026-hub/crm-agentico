import { describe, expect, it } from 'vitest';

import { marcarSinCache } from './server/sin-cache.js';

/**
 * EL DOCUMENTO HTML NO SE CACHEA (07/11/2026).
 *
 * El defecto, medido con el usuario sobre Programación: tres deploys
 * seguidos salieron a producción —y se comprobó que el servidor servía solo
 * el código nuevo: un único sello de build en 30 pedidos, sin service worker,
 * y ningún bundle con rastros del código viejo— y su pantalla siguió
 * dibujando la versión de dos deploys atrás. La respuesta del documento salía
 * con `Etag` y sin `cache-control`, así que el navegador la guardaba con su
 * propia heurística y la servía sin preguntar; como el documento es el que
 * nombra los bundles con su hash, seguía ejecutando el JavaScript viejo.
 *
 * Se afirma sobre el EFECTO —qué cabecera queda puesta— y no sobre que la
 * función exista.
 */
describe('el documento no se cachea', () => {
  const eventoFalso = () => {
    /** @type {Record<string, string>} */
    const cabeceras = {};
    return {
      cabeceras,
      event: /** @type {any} */ ({
        setHeaders: (/** @type {Record<string, string>} */ nuevas) =>
          Object.assign(cabeceras, nuevas)
      })
    };
  };

  it('EL DEFECTO: la página sale con cache-control no-store', () => {
    const { cabeceras, event } = eventoFalso();
    marcarSinCache(event)({ html: '<html lang="es"></html>' });
    expect(cabeceras['cache-control']).toBe('no-store');
  });

  //  `no-cache` NO alcanza: el navegador igual guarda y revalida, y el ETag de
  //  adapter-node se repite entre builds cuando el documento no cambia de
  //  tamaño, así que un 304 devolvería otra vez el documento viejo.
  it('no alcanza con revalidar: tiene que decir no-store', () => {
    const { cabeceras, event } = eventoFalso();
    marcarSinCache(event)({ html: '' });
    expect(cabeceras['cache-control']).not.toBe('no-cache');
    expect(cabeceras['cache-control']).not.toContain('max-age');
  });

  it('devuelve el html tal cual: es una cabecera, no una transformación', () => {
    const { event } = eventoFalso();
    const html = '<div>Para que el día salga completo</div>';
    expect(marcarSinCache(event)({ html })).toBe(html);
  });

  //  EL CABLE: la cabecera no sirve de nada si `handle` no la engancha. Es
  //  una afirmación sobre el archivo, porque levantar el servidor de
  //  SvelteKit en una prueba de vitest no entra en este arnés.
  it('y el handle la engancha en resolve', async () => {
    const { readFileSync } = await import('node:fs');
    const fuente = readFileSync('src/hooks.server.js', 'utf8');
    expect(fuente).toContain('resolve(event, { transformPageChunk: marcarSinCache(event) })');
  });
});
