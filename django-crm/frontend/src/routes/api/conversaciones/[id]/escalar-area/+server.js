import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/**
 * Escalar a un área (T22, contrato v3.3, 30/10/2026): quien la tiene -- o
 * nadie -- la pasa a un área de la empresa, con motivo y nota de lo que
 * validó. Cualquier operador; pasarla a una PERSONA sigue siendo reasignar.
 *
 * El autor sale de la sesión, nunca del navegador. Del navegador viene solo
 * el área (la valida el motor contra las de la empresa), el motivo, la nota
 * y la clave de la operación.
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
  const texto = (/** @type {unknown} */ v) => (typeof v === 'string' ? v.trim() : '');
  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/escalar-area`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        ...autorDeSesion(locals),
        area: texto(cuerpo?.area),
        motivo: texto(cuerpo?.motivo),
        nota: texto(cuerpo?.nota),
        clave_operacion: texto(cuerpo?.clave_operacion) || undefined
      })
    });
    const datos = await resp.json().catch(() => ({}));
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
