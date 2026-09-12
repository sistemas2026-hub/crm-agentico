import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Aprueba una propuesta: escribe la herramienta al catalogo real (ver
 * nucleo/config/editor.py::aprobar_herramienta_propuesta) y recien
 * despues marca la propuesta como 'aprobada'. Un borrador mal armado
 * vuelve como error 400 con el motivo exacto -- no se cuela nunca.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede aprobar esto.' }, { status: 403 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/configuracion/propuestas/${params.id}/aprobar`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // 'revisado_por' sale de la sesion, nunca del cliente -- mismo
      // criterio que 'marcado_por'/'revisado_por' en el resto del proyecto.
      body: JSON.stringify({ tenant, revisado_por: locals.user.email })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo aprobar la propuesta' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
