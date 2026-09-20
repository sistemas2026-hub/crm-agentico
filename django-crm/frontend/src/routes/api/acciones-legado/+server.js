import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Las acciones propuestas que quedaron pendientes. Ver nucleo/canales/api.py:
 * GET /acciones/propuestas.
 *
 * Existen 36 de antes de que las acciones se vincularan a una conversación
 * (A5), y hasta ahora eran invisibles: el endpoint estaba y ninguna pantalla
 * lo consumía. Sin superficie, la revisión humana que el gate G3 exige no se
 * puede hacer — ni siquiera para decidir cuál cancelar.
 *
 * La lista NO trae `argumentos`: ahí están los valores reales sin enmascarar
 * (teléfono, cédula, dirección) con los que se iba a escribir afuera. Para
 * revisar una acción alcanza su resumen. Eso lo decide el motor, no este
 * proxy.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, fetch, url }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const estado = url.searchParams.get('estado') || 'pendiente';
  try {
    const resp = await fetch(
      `${baseUrl}/acciones/propuestas?tenant=${encodeURIComponent(tenant)}` +
        `&estado=${encodeURIComponent(estado)}`,
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
