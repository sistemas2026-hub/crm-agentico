import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy de solo lectura hacia /centro-mando del motor. Lo usa la pantalla
 * para refrescarse sola cada pocos segundos sin recargar (el `load` del
 * servidor resuelve la primera pintada; esto, las siguientes).
 *
 * Mismo patron que /api/agentes: el tenant sale de PRIVATE_ASISTENTE_TENANT
 * en el servidor, nunca del cliente -- que el navegador pudiera elegir de que
 * empresa son los datos convertiria una pantalla interna en un selector de
 * organizaciones ajenas.
 */

/** @type {import('./$types').RequestHandler} */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  // Unico parametro que viaja del cliente: cuantos minutos cuentan como
  // "ahora mismo". El motor lo acota igual (1..120), asi que un valor
  // absurdo no barre mas tabla de la cuenta.
  const ventana = url.searchParams.get('ventana') || '10';

  try {
    const resp = await fetch(
      `${baseUrl}/centro-mando?tenant=${encodeURIComponent(tenant)}&ventana=${encodeURIComponent(ventana)}`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo cargar el panorama' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
