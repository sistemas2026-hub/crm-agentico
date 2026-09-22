import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Cómo está el equipo del cliente ahora: enlace y potencia óptica.
 * Ver nucleo/canales/api.py: GET /conversaciones/<id>/optica.
 *
 * SÓLO LECTURA. Reiniciar un equipo corta el servicio de alguien y no pasa
 * por acá.
 *
 * `?forzar=1` salta el caché de cinco minutos del motor. Es lo que manda el
 * botón "Consultar ahora" -- y por eso el parámetro se reenvía en vez de
 * fijarse acá: una recarga normal de la pantalla tiene que poder usar el
 * caché, porque el proveedor pide expresamente no consultar en bucle.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch, params, url }) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const forzar = url.searchParams.get('forzar') === '1' ? '&forzar=1' : '';

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/optica` +
        `?tenant=${encodeURIComponent(tenant)}${forzar}`,
      { headers: headersMotor() }
    );
    return json(await resp.json(), { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json(
      { error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 }
    );
  }
}
