import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Proxy hacia el motor: que dice la documentacion interna sobre un texto.
 * Mismo patron que el resto de /api/conversaciones -- el browser nunca conoce
 * la URL real del motor ni necesita CORS.
 *
 * Va por POST, igual que el endpoint del motor: el texto suele ser el mensaje
 * de un cliente y en una URL terminaria escrito en los logs de acceso.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { texto, rol } = await request.json();
  if (!texto || !texto.trim()) {
    return json({ error: 'Falta el texto a consultar' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/sugerencias`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // El rol decide que documentos se pueden ver. Por defecto el del motor
      // ('soporte'): quien llega aca esta autenticado en el CRM y atiende.
      body: JSON.stringify(rol ? { tenant, texto, rol } : { tenant, texto })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo consultar la documentacion' },
        { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
