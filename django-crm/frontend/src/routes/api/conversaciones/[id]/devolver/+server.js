import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Devolverle la conversacion a la IA. La inversa de /intervenir.
 * Ver nucleo/canales/api.py: POST /conversaciones/<id>/devolver.
 *
 * NO le envia nada al cliente: solo suelta el control. Responder y devolver en
 * el mismo gesto sigue existiendo y es otra ruta (el modo del compositor) --
 * son dos intenciones distintas y conviene que se pidan por separado.
 *
 * El autor sale de la SESION, nunca del navegador; la clave de operacion la
 * genera la pantalla por clic, para que un reintento no devuelva dos veces.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch, request }) {
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
  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/devolver`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        ...autorDeSesion(locals),
        clave_operacion:
          typeof cuerpo?.clave_operacion === 'string' ? cuerpo.clave_operacion : undefined
      })
    });
    const datos = await resp.json().catch(() => ({}));
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
