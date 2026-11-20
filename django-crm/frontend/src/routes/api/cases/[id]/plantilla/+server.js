import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion, claveIdempotencia } from '$lib/server/v2/autor.js';
import { replyToTicket } from '$lib/server/v2/tickets.js';

/**
 * Una plantilla aprobada de WhatsApp desde la pantalla del TICKET (28/10/2026).
 * Ver nucleo/canales/api.py: POST /casos/<id>/plantilla.
 *
 * Es la salida que faltaba cuando la respuesta de texto vuelve con «no le llegó
 * al cliente»: casi siempre pasaron más de 24 h desde su último mensaje, y fuera
 * de esa ventana WhatsApp sólo deja mandar plantillas aprobadas.
 *
 * El motor elige la conversación del caso, vuelve a validar la plantilla, la
 * guarda, la entrega, la copia al ticket del ISP y --si Meta la aceptó-- marca
 * la primera respuesta. Acá, además, queda en el historial del ticket del CRM,
 * como una respuesta de texto; con `sinPrimeraRespuesta`, porque esa la marca
 * el motor sólo si salió.
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
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const cuerpo = await request.json().catch(() => ({}));
  const plantilla = (cuerpo?.plantilla ?? '').trim();
  if (!plantilla) {
    return json({ error: 'Falta elegir una plantilla.' }, { status: 400 });
  }
  const variables = Array.isArray(cuerpo?.variables) ? cuerpo.variables.map(String) : [];

  /** @type {any} */
  let datos;
  let status;
  try {
    const resp = await fetch(`${baseUrl}/casos/${encodeURIComponent(params.id)}/plantilla`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        plantilla,
        variables,
        ...autorDeSesion(locals),
        clave_idempotencia: claveIdempotencia(cuerpo?.clave_idempotencia)
      }),
      signal: AbortSignal.timeout(20000)
    });
    status = resp.status;
    datos = await resp.json().catch(() => ({}));
  } catch {
    //  Sin respuesta NO es "no salió": pudo haber salido. Que no se reenvíe.
    return json(
      { error: 'No se pudo confirmar el envío. No la mandes de nuevo: si salió, la recibiría dos veces.', incierto: true },
      { status: 502 }
    );
  }

  //  201 = el motor la guardó (haya salido o no). Un reintento de la misma
  //  clave vuelve 200 con 'ya_existia' y ya está en el historial.
  if (status === 201 && datos?.texto) {
    try {
      await replyToTicket({ cookies }, params.id, { body: datos.texto, sinPrimeraRespuesta: true });
      datos.en_historial = true;
    } catch {
      datos.en_historial = false;
    }
  }
  return json(datos, { status });
}
