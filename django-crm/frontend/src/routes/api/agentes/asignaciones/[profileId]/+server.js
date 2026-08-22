import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

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
        headers: headersMotor({ 'Content-Type': 'application/json' }),
        // Se reenvia TODO lo que la pantalla mando, no solo los agentes.
        //
        // Esto solo pasaba 'roles', asi que el area y el usuario del sistema
        // externo se perdian aca en silencio: el motor contestaba 200 porque
        // desde su lado nunca llegaron esos campos, y la pantalla mostraba
        // "guardado" sobre un cambio que no ocurrio.
        //
        // Se me paso porque probe el endpoint del motor directamente -- donde
        // andaba-- y no por el camino que de verdad usa la pantalla. Un
        // intermediario que recorta el cuerpo no falla: miente.
        body: JSON.stringify({
          tenant,
          roles: cuerpo?.roles ?? [],
          ...(cuerpo?.area !== undefined ? { area: cuerpo.area } : {}),
          ...(cuerpo?.identidad_externa !== undefined
            ? { identidad_externa: cuerpo.identidad_externa }
            : {})
        })
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
