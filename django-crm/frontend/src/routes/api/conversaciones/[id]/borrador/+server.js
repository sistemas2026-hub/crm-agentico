import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * Un borrador de respuesta de la IA (30/10/2026). A PEDIDO, y NO envía nada:
 * el motor devuelve texto que la persona edita en el compositor y manda ella
 * (nucleo/seguimiento/borrador.py).
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }
  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/borrador`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ tenant }),
      // El modelo tiene 30 s en el motor; acá un poco más para que el error
      // que se ve sea el del motor y no un corte de este lado.
      signal: AbortSignal.timeout(40000)
    });
    const datos = await resp.json().catch(() => ({}));
    return json(datos, { status: resp.status });
  } catch {
    return json({ error: 'No se pudo pedir la sugerencia.' }, { status: 502 });
  }
}
