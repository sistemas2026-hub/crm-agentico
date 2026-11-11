import { json } from '@sveltejs/kit';
import {
  buscarEnMensajes,
  normalizarBusqueda,
  BUSQUEDA_MINIMO,
  BUSQUEDA_MAXIMO
} from '$lib/server/v2/busqueda-mensajes.js';

/**
 * Buscar en el contenido de los mensajes (11/11/2026), para el buscador de la
 * Bandeja. El navegador no habla con el motor: pasa por acá, que pone el
 * tenant de la sesión.
 *
 * Ruta estática dentro de `api/conversaciones/`: SvelteKit la prefiere a
 * `[id]`, así que «buscar» nunca se lee como el id de una conversación.
 *
 * El rango de `q` se mira acá también para no viajar al motor por nada; la
 * autoridad sigue siendo el motor. Un error del motor vuelve con su texto,
 * que es fijo y nunca cita lo buscado. Nada de esto va al log: `q` es texto
 * de un cliente.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, locals, fetch, request }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const q = normalizarBusqueda(url.searchParams.get('q'));
  if (q.length < BUSQUEDA_MINIMO || q.length > BUSQUEDA_MAXIMO) {
    return json(
      { error: `La búsqueda tiene que tener entre ${BUSQUEDA_MINIMO} y ${BUSQUEDA_MAXIMO} caracteres.` },
      { status: 400 }
    );
  }
  try {
    const { resultados, tope } = await buscarEnMensajes(locals, fetch, q, { signal: request.signal });
    return json({ resultados, tope });
  } catch (/** @type {any} */ err) {
    if (err?.name === 'AbortError') {
      return json({ error: 'El asistente tardó demasiado en buscar.' }, { status: 504 });
    }
    return json({ error: err?.message || 'No se pudo buscar en los mensajes.' }, { status: 502 });
  }
}
