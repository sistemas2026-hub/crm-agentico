import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Marcar/desmarcar una respuesta del agente como buen ejemplo de un caso --
 * base del manual de procedimientos (ver /manual). Mismo patron que
 * api/conversaciones/[id]/humano: proxy delgado hacia
 * nucleo/canales/api.py, POST|DELETE /conversaciones/<id>/mensajes/<id>/marcar.
 *
 * 'marcado_por' NUNCA viene del cliente: se toma de la sesion logueada
 * (locals.user.email), igual que cualquier dato de auditoria.
 */

function baseUrlYTenant() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { caso } = await request.json();
  if (!caso) {
    return json({ error: 'Falta el caso' }, { status: 400 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(
      `${cfg.baseUrl}/conversaciones/${params.id}/mensajes/${params.mensajeId}/marcar`,
      {
        method: 'POST',
        headers: headersMotor({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ tenant: cfg.tenant, caso, marcado_por: locals.user.email })
      }
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo marcar el ejemplo' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}

/** @type {import('./$types').RequestHandler} */
export async function DELETE({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(
      `${cfg.baseUrl}/conversaciones/${params.id}/mensajes/${params.mensajeId}/marcar` +
        `?tenant=${encodeURIComponent(cfg.tenant)}`,
      { method: 'DELETE', headers: headersMotor() }
    );
    if (!resp.ok) {
      const datos = await resp.json().catch(() => ({}));
      return json({ error: datos.error || 'No se pudo desmarcar el ejemplo' }, { status: resp.status });
    }
    return new Response(null, { status: 204 });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
