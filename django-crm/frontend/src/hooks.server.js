import { sequence } from '@sveltejs/kit/hooks';
import * as Sentry from '@sentry/sveltekit';
import { marcarSinCache } from '$lib/server/sin-cache.js';
import { atenderSesion } from '$lib/server/sesion.js';

/**
 * SvelteKit server hooks.
 *
 * La sesión (cookies con JWT, renovación, empresa, guarda de ruta) vive en
 * `$lib/server/sesion.js`, no acá, desde el 11/11/2026: este archivo no se
 * puede importar fuera de SvelteKit, así que doscientas líneas de
 * autenticación corrieron sin una sola prueba hasta que una carrera en la
 * renovación del token cerró sesiones en producción. Lo que decide, se prueba;
 * lo que no se puede probar, no decide. Ver la cabecera de ese archivo.
 */

export const handleError = Sentry.handleErrorWithSentry();

export const handle = sequence(Sentry.sentryHandle(), async function _handle({ event, resolve }) {
  await atenderSesion(event);

  //  EL DOCUMENTO NO SE CACHEA (07/11/2026): tres deploys seguidos salieron y
  //  la pantalla del usuario siguió corriendo el JavaScript de dos atrás. Ver
  //  `$lib/server/sin-cache.js`, que tiene la medición y el porqué del
  //  `no-store`.
  return resolve(event, { transformPageChunk: marcarSinCache(event) });
});
