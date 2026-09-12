import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Proxy hacia el rol 'configuracion_guiada' del motor -- mismo patron que
 * /api/asistente y /api/simulador-whatsapp, pero gateado a ADMIN: este rol
 * puede sondear URLs externas arbitrarias y proponer herramientas nuevas
 * (ver tenants/rapilink.config.yaml). El gate de ADMIN es la UNICA barrera
 * real de "quien puede llegar aca" -- el motor no conoce roles de
 * BottleCRM, asi que si esta ruta no lo filtrara, cualquier miembro logueado
 * podria hablarle a este rol escribiendo la URL a mano.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, locals, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (locals.profile?.role !== 'ADMIN') {
    return json({ error: 'Solo un administrador puede usar esto.' }, { status: 403 });
  }

  const { mensaje } = await request.json();
  if (!mensaje) {
    return json({ error: 'Falta el mensaje' }, { status: 400 });
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
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        rol: 'configuracion_guiada',
        // Una sesion por persona (no por telefono, como el simulador): dos
        // ADMIN configurando cosas distintas no deben pisarse el historial.
        identificador_sesion: `configuracion-guiada:${locals.user.id}`,
        mensaje,
        canal: 'configuracion-guiada'
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
