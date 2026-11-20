import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

/**
 * «Leída» / «Marcar como no leída» (11/11/2026), como WhatsApp Business. Ver
 * nucleo/canales/api.py: POST /conversaciones/<id>/leida.
 *
 * La marca es del EQUIPO, no de cada persona: no viaja autor. Pero exige
 * sesión igual -- una ruta del CRM que escribe no queda abierta.
 *
 * `leida` se manda como BOOLEANO estricto: solo `true` es leída. Un "false"
 * en texto que pasara de largo sería verdadero en el motor... que por eso
 * también lo rechaza; acá se normaliza para que nunca llegue así.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, params, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }
  const cuerpo = await request.json().catch(() => ({}));
  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/leida`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ tenant, leida: cuerpo?.leida === true })
    });
    const datos = await resp.json().catch(() => ({}));
    /* `marcada_en` con el reloj de ESTE servidor, el mismo que sella
       `sondeadoEn` en la carga de la cola: una cola cargada después ya ve la
       marca, y una de antes no. Compararla con la hora del navegador o con la
       de la base mezclaría tres relojes (lib/conversaciones/lectura.js). */
    if (resp.ok) datos.marcada_en = new Date().toISOString();
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
