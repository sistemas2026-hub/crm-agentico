import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';

/** Lo más largo que se acepta como motivo. Es un registro de auditoría, no
 *  un documento: un texto mayor es casi seguro un pegado por error. */
export const MOTIVO_MAXIMO = 500;

/**
 * Rechazar una acción que la IA propuso, CON MOTIVO  --  12/11/2026
 * Ver nucleo/canales/api.py: POST /acciones/propuestas/<id>/rechazar.
 *
 * POR QUÉ EXISTE. La Bandeja aprobaba pero no rechazaba (auditoría del menú,
 * §2 «Conversaciones» y §4 ítem 2). La autonomía ganada de cada herramienta
 * se mide con lo que una persona decidió sobre sus propuestas
 * (nucleo/persistencia/autonomia_ganada.py: `revisadas` y `rechazadas`), y
 * sin un «no» la tasa de aprobación solo podía subir. Rechazar acá deja la
 * fila en `rechazada` con `revisado_en`, que es exactamente lo que esa
 * medición cuenta.
 *
 * DOS COSAS QUE EL MOTOR NO EXIGE Y ESTE PROXY SÍ. El endpoint del motor
 * acepta un rechazo sin `revisado_por` y sin `motivo`. Acá se cierran las dos:
 *  - quién rechaza sale de la SESIÓN, nunca del cuerpo que arma el navegador
 *    (contrato del relevo §3.4): un rechazo sin responsable no se audita;
 *  - el motivo es obligatorio: un «no» sin porqué no le enseña nada a nadie,
 *    ni a la persona que revise la evidencia ni a quien corrija el agente.
 *
 * Rechazar no ejecuta nada ni le escribe al cliente (contrato T14 y P4): la
 * acción queda congelada en `rechazada` y, si hace falta otra, la IA la
 * vuelve a proponer.
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

  const cuerpo = await request.json().catch(() => ({}));
  const motivo = typeof cuerpo?.motivo === 'string' ? cuerpo.motivo.trim() : '';
  if (!motivo) {
    return json({ error: 'Escribí por qué la rechazás.' }, { status: 400 });
  }
  if (motivo.length > MOTIVO_MAXIMO) {
    return json({ error: `El motivo no puede pasar de ${MOTIVO_MAXIMO} caracteres.` },
      { status: 400 });
  }

  const { autor: quien } = autorDeSesion(locals);
  if (!quien) {
    return json({ error: 'No se pudo identificar quién rechaza.' }, { status: 400 });
  }

  try {
    const resp = await fetch(
      `${baseUrl}/acciones/propuestas/${encodeURIComponent(params.accion)}/rechazar`,
      {
        method: 'POST',
        headers: { ...headersMotor(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant, revisado_por: quien, motivo })
      }
    );
    const datos = await resp.json().catch(() => ({}));
    // El 409 viaja con su `estado`: si otra persona ya la aprobó o la rechazó,
    // la pantalla relee y muestra cómo quedó en vez de un error genérico.
    return json(datos, { status: resp.status });
  } catch {
    return json({ error: 'No se pudo contactar al asistente.' }, { status: 502 });
  }
}
