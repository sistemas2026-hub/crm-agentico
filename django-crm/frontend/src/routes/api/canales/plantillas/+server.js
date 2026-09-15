import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Las plantillas que Meta tiene aprobadas para esta cuenta, con su texto.
 * Ver nucleo/canales/api.py: GET /canales/plantillas.
 *
 * Son la única forma de escribirle a alguien con la ventana de 24 h cerrada,
 * así que esto se pide recién cuando hace falta —no en cada carga del hilo—:
 * es una llamada en vivo a Meta y la mayoría de las conversaciones se
 * atienden con la ventana abierta.
 *
 * A diferencia de los límites de media, acá un fallo SÍ se cuenta: si no se
 * pudieron leer, quien está mirando una ventana cerrada no tiene ninguna otra
 * salida, y un selector vacío sin explicación se lee como "no hay plantillas"
 * cuando en realidad no se pudo preguntar.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/canales/plantillas?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() }
    );
    const datos = await resp.json();
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json(
      { error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 }
    );
  }
}
