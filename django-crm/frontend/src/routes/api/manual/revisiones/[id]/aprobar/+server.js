import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Aprobar una revision del supervisor -- la persona confirma que el
 * veredicto es correcto y que el aporte sirve para el manual. Proxy hacia
 * nucleo/canales/api.py:POST /manual/revisiones/<id>/aprobar.
 *
 * 'revisado_por' NUNCA viene del cliente: se toma de la sesion logueada,
 * igual que 'marcado_por' en /api/conversaciones/.../marcar.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/manual/revisiones/${params.id}/aprobar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tenant, revisado_por: locals.user.email })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo aprobar la revision' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
