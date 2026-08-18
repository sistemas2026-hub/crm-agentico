import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Los tipos de caso con que el asistente clasifica cada conversación
 * (tenant_config.manual.casos). Se manda la lista COMPLETA, no un caso
 * suelto: así la pantalla envía lo que quedó en ella y el motor valida el
 * conjunto entero (ver nucleo/config/editor.py::_mutar_casos_manual).
 *
 * Mismo gate de ADMIN que el resto de la configuración del asistente: esta
 * lista es el enum que ve el modelo, y de ella cuelga el agendamiento
 * automático de visitas.
 */

/** @type {import('./$types').RequestHandler} */
export async function PUT({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede editar los tipos de caso.' },
      { status: 403 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json();

  try {
    const resp = await fetch(`${baseUrl}/manual/casos`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ casos: cuerpo.casos, tenant })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      // El motor devuelve el motivo exacto (que falta 'otro', que hay un
      // nombre inválido, que el agendamiento depende de un caso que se está
      // borrando). Se pasa tal cual: es lo único que le dice a quien edita
      // qué tiene que corregir.
      return json({ error: datos.error || 'No se pudieron guardar los casos' },
        { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 });
  }
}
