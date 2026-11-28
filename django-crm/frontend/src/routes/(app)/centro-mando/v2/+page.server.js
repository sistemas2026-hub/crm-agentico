import { redirect } from '@sveltejs/kit';

/**
 * `/centro-mando/v2` REDIRIGE A `/centro-mando`.
 *
 * La oficina virtual dejó de ser una ruta aparte: es el centro de mando. Esta
 * redirección existe para no romper lo que ya apunta a `/v2` —la ficha del
 * objetivo, el spike de Three.js, un enlace guardado en el navegador de
 * alguien— y para que nadie se quede mirando un 404 preguntándose si lo
 * desplegado está roto.
 *
 * 308 y no 302: el cambio es permanente y vale decirlo, así un cliente que
 * cachea no vuelve a preguntar.
 *
 * @type {import('./$types').PageServerLoad}
 */
export function load({ url }) {
  redirect(308, '/centro-mando' + (url.search || ''));
}
