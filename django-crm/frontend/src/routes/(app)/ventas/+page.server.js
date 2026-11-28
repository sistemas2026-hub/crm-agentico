/**
 * El embudo de ventas (12/11/2026).
 *
 * El periodo viaja en la URL (?dias=30, o ?desde=…&hasta=…): un embudo se
 * comparte por chat y volver atrás en el navegador tiene que hacer lo que uno
 * espera. Todo número viene calculado de Django; ver `lib/server/v2/ventas.js`.
 */
import { leerEmbudo, periodoDe } from '$lib/server/v2/ventas.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, url }) {
  return await leerEmbudo(cookies, periodoDe(url.searchParams));
}
