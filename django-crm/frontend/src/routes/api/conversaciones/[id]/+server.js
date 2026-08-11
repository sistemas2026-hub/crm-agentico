import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

/**
 * Proxy hacia el motor para continuar una conversación abierta desde la
 * bandeja -- mismo patrón que /api/simulador-whatsapp, pero la identidad
 * (usuario_externo, rol_efectivo, canal) viene de la conversación ya
 * cargada en la página, no de un campo de teléfono a mano: seguimos EL
 * MISMO hilo, no arrancamos uno nuevo.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { mensaje, usuario_externo, rol_efectivo, canal } = await request.json();
  if (!mensaje || !usuario_externo) {
    return json({ error: 'Falta mensaje o usuario_externo' }, { status: 400 });
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tenant,
        rol: rol_efectivo || 'cliente_final',
        identificador_sesion: usuario_externo,
        mensaje,
        // Se preserva el canal original de la conversacion en vez de
        // asumir uno: no se re-etiqueta un hilo real como simulado o
        // viceversa solo por responder desde acá.
        canal: canal || 'whatsapp-simulado'
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'El asistente no respondio' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
