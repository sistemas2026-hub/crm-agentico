import { redirect } from '@sveltejs/kit';

/**
 * Esta pantalla ya no existe: area, agentes y usuario externo se editan en
 * Equipo y acceso, en la misma fila de cada persona.
 *
 * Por que redirige en vez de quedarse como estaba: eran DOS editores del
 * mismo dato. Se daba de alta a alguien en un lugar y se lo corregia en otro,
 * que fue exactamente la queja que origino el rediseño -- y con dos
 * pantallas escribiendo lo mismo, la que se use menos se queda atras y
 * empieza a mostrar un estado que no es.
 *
 * Redirige y no devuelve 404 a proposito: el enlace vive en /agentes y puede
 * estar guardado en el navegador de alguien. Llevarlo al lugar correcto es
 * mejor que decirle que no hay nada.
 *
 * @type {import('./$types').PageServerLoad}
 */
export function load() {
  redirect(307, '/team');
}
