import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion, claveIdempotencia } from '$lib/server/v2/autor.js';
import { apiRequest } from '$lib/api-helpers.js';

/**
 * Nota interna: queda en el hilo para el equipo y NO se le envía al cliente.
 * Ver nucleo/canales/api.py: POST /conversaciones/<id>/nota.
 *
 * Ruta aparte de la que responde, a propósito. La garantía de que una nota no
 * salga al cliente no es una bandera dentro de un cuerpo JSON que alguien
 * puede armar mal: es que este camino no toca el canal en ningún punto.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch, request, cookies }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json(
      { error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 }
    );
  }

  const cuerpo = await request.json().catch(() => ({}));
  const mensaje = (cuerpo?.mensaje ?? '').trim();
  if (!mensaje) {
    return json({ error: 'La nota está vacía.' }, { status: 400 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/nota`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // El autor sale de la sesión: una nota firmada por quien dice el
      // navegador no sirve para nada.
      body: JSON.stringify({ tenant, mensaje, ...autorDeSesion(locals) })
    });
    const datos = await resp.json();
    // MENCIONES (30/10/2026): «@luis mirá esta» le avisa a Luis en la
    // campanita, con el enlace a la conversación. La nota vive en el motor y
    // las notificaciones en el CRM, así que el aviso sale de acá, DESPUÉS de
    // que la nota quedó guardada. Si falla, la nota ya está: no se tumba por
    // un aviso, y se dice cuántos salieron para que la pantalla no prometa.
    if (resp.ok && mensaje.includes('@')) {
      try {
        const r = await apiRequest('/notifications/mencion-conversacion/',
          { method: 'POST', body: { conversation_id: params.id, texto: mensaje } }, { cookies });
        datos.avisados = r?.avisados ?? 0;
      } catch {
        datos.avisados = null;
      }
    }
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
