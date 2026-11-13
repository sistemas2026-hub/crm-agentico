/**
 * EL DOCUMENTO HTML NO SE CACHEA (07/11/2026).
 *
 * Sin esto la respuesta de una página sale con `Etag` y SIN `cache-control`,
 * y ahí el navegador decide solo: guarda el documento con una heurística
 * propia y lo sirve de su caché sin preguntar. El documento es el que nombra
 * los bundles con su hash, así que quien ya visitó la pantalla sigue
 * ejecutando el JavaScript del deploy anterior —con recarga incluida— y no
 * tiene manera de enterarse.
 *
 * Medido ese día, con el usuario sobre Programación: el servidor servía un
 * solo sello de build, el nuevo, sin réplicas viejas (30 pedidos, un solo
 * `version.json`) y sin service worker (no hay, y `app.js` no registra
 * ninguno); los bundles servidos tenían solo el código nuevo —ningún archivo
 * con `mc-titulo` ni con «nunca se conectó»—, y aun así su pantalla seguía
 * dibujando la versión de dos deploys atrás.
 *
 * `no-store` y no `no-cache`: con `no-cache` el navegador igual guarda y
 * revalida, y el ETag de adapter-node se repite entre builds cuando el
 * documento no cambia de tamaño, así que un 304 devolvería otra vez lo viejo.
 * El costo es un documento por visita; los bundles de `/_app/immutable/`
 * siguen cacheados para siempre, que es donde está el peso.
 *
 * Vive acá y no en `hooks.server.js` para poder probarlo: ese archivo importa
 * `$env/dynamic/public`, que fuera de SvelteKit no resuelve, así que una
 * prueba no puede cargarlo.
 *
 * @param {{ setHeaders: (c: Record<string, string>) => void }} event
 */
export function marcarSinCache(event) {
  /**
   * Solo el documento: un endpoint o un archivo estático no pasan por
   * `transformPageChunk`, así que no los toca.
   * @param {{ html: string }} entrada
   */
  return ({ html }) => {
    event.setHeaders({ 'cache-control': 'no-store' });
    return html;
  };
}
