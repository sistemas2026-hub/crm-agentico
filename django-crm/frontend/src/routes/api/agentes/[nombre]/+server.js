import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Editar/borrar un agente puntual. Mismo gate de ADMIN que POST /api/agentes
 * -- ver ese archivo para el porque.
 */

function baseUrlYTenant() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/** @type {import('./$types').RequestHandler} */
export async function PUT({ params, request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede editar agentes.' }, { status: 403 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json();

  try {
    const resp = await fetch(`${cfg.baseUrl}/agentes/${encodeURIComponent(params.nombre)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cuerpo, tenant: cfg.tenant })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo editar el agente' }, { status: resp.status });
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
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede borrar agentes.' }, { status: 403 });
  }

  const cfg = baseUrlYTenant();
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(
      `${cfg.baseUrl}/agentes/${encodeURIComponent(params.nombre)}?tenant=${encodeURIComponent(cfg.tenant)}`,
      { method: 'DELETE' }
    );
    if (!resp.ok) {
      const datos = await resp.json().catch(() => ({}));
      return json({ error: datos.error || 'No se pudo borrar el agente' }, { status: resp.status });
    }
    return new Response(null, { status: 204 });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
