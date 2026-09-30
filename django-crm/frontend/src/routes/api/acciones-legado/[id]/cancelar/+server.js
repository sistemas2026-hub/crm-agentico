import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Cancelar una acción que quedó obsoleta. Ver nucleo/canales/api.py:
 * POST /acciones/propuestas/<id>/cancelar.
 *
 * ES EL ÚNICO VERBO QUE ESTA PANTALLA EXPONE. No hay proxy de `aprobar`, a
 * propósito: aprobar es ejecutar, y ejecutar una acción sin conversación —con
 * los argumentos congelados de hace semanas y sin revalidación— es lo que X24
 * prohíbe. El motor además la rechaza con 409, así que esto no es la única
 * defensa; es que no haya ni por dónde intentarlo.
 *
 * Quien cancela va con su nombre: una cancelación administrativa sin nombre no
 * se puede auditar, y lo toma de la sesión en vez de creerle al navegador.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ locals, fetch, params, request }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const cuerpo = await request.json().catch(() => ({}));
  const motivo = (cuerpo?.motivo || '').trim();
  if (!motivo) {
    return json({ error: 'Falta el motivo de la cancelación.' }, { status: 400 });
  }

  const { autor: quien } = autorDeSesion(locals);
  if (!quien) {
    return json({ error: 'No se pudo identificar quién cancela.' }, { status: 400 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/acciones/propuestas/${encodeURIComponent(params.id)}/cancelar`,
      {
        method: 'POST',
        headers: { ...headersMotor(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant, motivo, cancelada_por: quien })
      }
    );
    return json(await resp.json(), { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json(
      { error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 }
    );
  }
}
