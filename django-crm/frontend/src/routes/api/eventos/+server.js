import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Proxy del flujo incremental de eventos del motor.
 *
 * La empresa sale de LA SESIÓN (`tenantDeLaSesion`), en el servidor y nunca
 * del cliente: que el navegador pudiera elegir de qué empresa son los eventos
 * convertiría esta pantalla en un visor de operaciones ajenas.
 *
 * Lo único que viaja del cliente es el CURSOR, y es inofensivo: el motor lo
 * usa para filtrar hacia adelante dentro de la empresa ya resuelta acá. Un
 * cursor inventado devuelve menos eventos, nunca los de otro.
 *
 * EL ORDEN AL ARRANCAR, que no es el que parece:
 *
 *   1) pedir el cursor acá, sin `desde`  -> devuelve la frontera y 0 eventos
 *   2) pedir la foto a /api/centro-mando
 *
 * Lo que ocurra entre ambas lecturas llega por los DOS caminos: sale en la
 * foto y además lo entrega el cursor. Eso es un duplicado, y deduplicar por
 * `id` es trivial. Al revés habría un HUECO, y un hueco no se recupera.
 * Duplicar es seguro; perder no.
 */

/** @type {import('./$types').RequestHandler} */
export async function GET({ url, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado' }, { status: 500 });
  }

  const partes = new URLSearchParams({ tenant });
  const desde = url.searchParams.get('desde');
  if (desde) partes.set('desde', desde);
  const limite = url.searchParams.get('limite');
  if (limite) partes.set('limite', limite);

  try {
    const resp = await fetch(`${baseUrl}/eventos?${partes}`, { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo leer el flujo' },
        { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    // El motor caído NO se convierte en «servile los datos de otra empresa»:
    // se devuelve el error y el cliente conserva su cursor para reintentar.
    return json({ error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 });
  }
}
