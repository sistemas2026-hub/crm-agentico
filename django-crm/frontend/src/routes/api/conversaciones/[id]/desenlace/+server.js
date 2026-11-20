import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Ponerle desenlace a una conversacion que se cerro sin uno (B6, §3.5).
 *
 * Los cierres por confirmacion del cliente y por inactividad dejan el codigo
 * en NULL a proposito: ahi nadie eligio nada. Esta es la otra mitad de esa
 * frase del contrato -- "se completan despues si una persona revisa".
 *
 * NO es la ruta hermana 'resolver', y confundirlas cambia lo que le pasa al
 * cliente:
 *
 *   resolver   la conversacion se cierra AHORA, con su desenlace
 *   desenlace  ya estaba cerrada; solo se dice en que termino
 *
 * El motor responde 409 si ya tiene desenlace. Se pasa tal cual: pisar el que
 * puso otra persona seria reescribir el pasado en silencio.
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
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/desenlace`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      // Quién lo completa sale de la sesión, nunca del cuerpo del navegador.
      body: JSON.stringify({
        tenant,
        ...autorDeSesion(locals),
        desenlace: cuerpo?.desenlace,
        nota: cuerpo?.nota,
        clave_operacion: cuerpo?.clave_operacion
      })
    });
    const datos = await resp.json();
    if (!resp.ok) {
      return json({ error: datos.error || 'No se pudo guardar' }, { status: resp.status });
    }
    return json(datos);
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
