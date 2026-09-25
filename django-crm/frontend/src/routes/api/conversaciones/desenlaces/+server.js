import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * El catalogo de cierre, tal como lo da el motor (B6).
 *
 * La pantalla NO trae su propia lista. Es la misma razon por la que los
 * estados de una accion tampoco se escriben dos veces: una copia en el
 * frontend se desincroniza el dia que alguien agrega un codigo desde la
 * configuracion, y entonces la pantalla ofrece algo que el motor rechaza --o
 * peor, deja de ofrecer algo valido y nadie lo nota.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json(
      { error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 }
    );
  }

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/desenlaces?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor({}) }
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
