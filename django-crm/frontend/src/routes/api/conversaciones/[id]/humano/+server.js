import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { autorDeSesion, claveIdempotencia } from '$lib/server/v2/autor.js';

/**
 * Proxy para que un agente humano responda directo en una conversacion ya
 * escalada -- a diferencia de /api/conversaciones/[id] (que simula al
 * cliente y le contesta el bot), esto NUNCA pasa por el modelo: guarda tal
 * cual lo que el agente tipeo. Ver nucleo/canales/api.py:
 * POST /conversaciones/<id>/mensajes.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const { mensaje, clave_idempotencia, devolver_al_asistente = false } = await request.json();
  if (!mensaje) {
    return json({ error: 'Falta el mensaje' }, { status: 400 });
  }
  // Devolver a la IA EXIGE que la clave venga de la pantalla, y acá no se
  // inventa una. claveIdempotencia() genera un uuid cuando el valor no sirve:
  // para un envío normal eso es mejor que nada, pero en T6 significaría que
  // dos intentos del mismo envío viajan con claves distintas -- y el segundo
  // le llega al cliente como un mensaje nuevo. Fallar acá es lo correcto:
  // el motor responde lo mismo, y así el error no queda enmascarado por una
  // clave que el proxy fabricó.
  const CLAVE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (devolver_al_asistente && !CLAVE.test(String(clave_idempotencia ?? ''))) {
    return json(
      { error: 'Devolver al asistente requiere clave_idempotencia.', codigo: 'clave_requerida' },
      { status: 400 }
    );
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/mensajes`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // Autor de la sesión (D2) y la clave que generó la pantalla: reintentar
      // con la misma clave reintenta la entrega, no crea otra fila (D15).
      body: JSON.stringify({
        tenant,
        mensaje,
        ...autorDeSesion(locals),
        clave_idempotencia: claveIdempotencia(clave_idempotencia),
        devolver_al_asistente: Boolean(devolver_al_asistente)
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo guardar la respuesta' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
