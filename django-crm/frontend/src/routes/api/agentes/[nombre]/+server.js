import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Editar/borrar un agente puntual. Mismo gate de ADMIN que POST /api/agentes
 * -- ver ese archivo para el porque.
 */

async function baseUrlYTenant(locals, fetch) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
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

  const cfg = await baseUrlYTenant(locals, fetch);
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json();

  try {
    const resp = await fetch(`${cfg.baseUrl}/agentes/${encodeURIComponent(params.nombre)}`, {
      method: 'PUT',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // Quien lo edita sale de la SESION (auditoria B1, 04/11/2026).
      body: JSON.stringify({ ...cuerpo, tenant: cfg.tenant, ...autorDeSesion(locals),
                             autor_rol: locals.profile?.role ?? '' })
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

  const cfg = await baseUrlYTenant(locals, fetch);
  if (!cfg) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(
      //  El autor va en la query porque un DELETE no lleva cuerpo: el motor lo
      //  anota en el historial de la config (13/11/2026). Sale de la sesion.
      `${cfg.baseUrl}/agentes/${encodeURIComponent(params.nombre)}?${new URLSearchParams({
        tenant: cfg.tenant, autor: autorDeSesion(locals).autor })}`,
      { method: 'DELETE', headers: headersMotor() }
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
