import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Aprobar una acción, que es EJECUTARLA.
 * Ver nucleo/canales/api.py: POST /acciones/propuestas/<id>/aprobar.
 *
 * Quién aprueba sale de la SESIÓN autenticada, nunca del cuerpo que arma el
 * navegador (§3.4): una ejecución firmada por quien dice el cliente HTTP no
 * prueba nada, y esto escribe en sistemas externos.
 *
 * Este proxy no decide nada más. Las cuatro condiciones —acción pendiente, en
 * plazo, conversación abierta, revalidación cumplida— las comprueba el motor,
 * y el estado que devuelve puede no ser el que la pantalla esperaba: una
 * `desconocida` no es ni hecha ni fallada.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ locals, fetch, params }) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const { autor: quien } = autorDeSesion(locals);
  if (!quien) {
    return json({ error: 'No se pudo identificar quién aprueba.' }, { status: 400 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/acciones/propuestas/${encodeURIComponent(params.accion)}/aprobar`,
      {
        method: 'POST',
        headers: { ...headersMotor(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant, revisado_por: quien })
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
