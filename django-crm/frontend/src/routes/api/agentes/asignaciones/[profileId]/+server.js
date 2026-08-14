import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Que agentes puede usar un colaborador. Mismo gate de ADMIN que crear o
 * editar un agente (ver /api/agentes/+server.js): decidir a que datos accede
 * una persona es un cambio de superficie de seguridad, no una preferencia.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function PUT({ params, request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede asignar agentes.' }, { status: 403 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json();

  try {
    const resp = await fetch(
      `${baseUrl}/agentes/asignaciones/${encodeURIComponent(params.profileId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles: cuerpo?.roles ?? [], tenant })
      }
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudieron guardar los agentes' },
        { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
