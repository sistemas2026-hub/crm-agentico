import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { rolDeSesion } from '$lib/server/v2/operadores.js';

/**
 * Reiniciar el equipo del cliente. Corta el servicio de alguien.
 * Ver nucleo/canales/api.py: POST /conversaciones/<id>/equipo/reiniciar.
 *
 * QUIÉN PIDE Y CON QUÉ ROL LO ARMA ESTE PROXY, DESDE LA SESIÓN -- nunca el
 * navegador. Es el mismo mecanismo que /reasignar, y es lo que hace que la
 * comprobación del motor signifique algo: si el id del actor viniera en el
 * cuerpo, quien llama elegiría contra quién se compara.
 *
 * El diálogo de confirmación de la pantalla NO es la garantía: quien llame
 * esta ruta directo no lo ve. La garantía son las cuatro condiciones del
 * motor -- motivo, control humano, dueño o ADMIN, conversación abierta.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ locals, fetch, params, request }) {
  if (!locals.user) return json({ error: 'No autenticado' }, { status: 401 });

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado.' }, { status: 500 });
  }

  const entrada = await request.json().catch(() => ({}));
  const motivo = String(entrada?.motivo ?? '').trim();
  // Se rechaza acá además de en el motor: no tiene sentido gastar una ida al
  // sistema del ISP para que vuelva un 400 que ya se sabía.
  if (!motivo) {
    return json({ error: 'Hace falta un motivo: queda en el expediente.' }, { status: 400 });
  }

  // El rol sale del perfil del JWT ya verificado, no del navegador. Ante la
  // duda queda 'USER': así el motor sólo deja actuar si además es el dueño.
  const rol = rolDeSesion(locals);

  try {
    const resp = await fetch(
      `${baseUrl}/conversaciones/${encodeURIComponent(params.id)}/equipo/reiniciar`,
      {
        method: 'POST',
        headers: { ...headersMotor(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant,
          motivo,
          autor: (locals.user.name || locals.user.email || '').trim(),
          autor_usuario_id: locals.user.id,
          autor_rol: rol
        })
      }
    );
    return json(await resp.json(), { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json(
      { error: err?.message || 'No se pudo contactar al asistente' },
      { status: 502 }
    );
  }
}
