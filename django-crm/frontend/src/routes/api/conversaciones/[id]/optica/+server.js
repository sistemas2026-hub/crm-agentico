import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

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
 * `?profundo=1` suma la consulta de ~10 s que trae temperatura, MAC, perfil y
 * las dos potencias de subida. Mismo criterio y misma razón para reenviarlo:
 * lo decide quien aprieta el botón, no este archivo.
 *
 * ESTE PROXY REENVÍA UNA LISTA, NO LO QUE VENGA. Un `url.search` a secas
 * pasaría cualquier parámetro que alguien ponga en la barra directo al motor.
 * La lista cuesta un renglón por parámetro y ese renglón es justamente el que
 * faltó: 'profundo' se agregó del lado del motor y del lado de la pantalla, y
 * acá no -- así que el motor nunca lo vio y las cuatro celdas se quedaron
 * vacías en producción. Visto el 22/09/2026. Al agregar un parámetro nuevo,
 * son TRES lugares, no dos.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch, params, url }) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const forzar = url.searchParams.get('forzar') === '1' ? '&forzar=1' : '';
  const profundo = url.searchParams.get('profundo') === '1' ? '&profundo=1' : '';

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/optica` +
        `?tenant=${encodeURIComponent(tenant)}${forzar}${profundo}`,
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
