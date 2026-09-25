import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { autorDeSesion } from '$lib/server/v2/autor.js';
import { operadoresDeLaOrg, rolDeSesion, validarReasignacion } from '$lib/server/v2/operadores.js';

/**
 * Reasignar una conversacion (B3.4, T4). Solo ADMIN.
 * Ver nucleo/canales/api.py: POST /conversaciones/<id>/reasignar.
 *
 * Lo unico que se toma del navegador es A QUIEN (el id), el motivo y la clave
 * de operacion. El actor y su rol salen de la sesion; el destino se valida
 * contra las personas activas de la organizacion y su nombre sale de ahi. El
 * motor vuelve a exigir el rol: esto es la primera barrera, no la unica.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, locals, fetch, request, cookies }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  const rol = rolDeSesion(locals);
  // El rol se mira ANTES de pedir nada: un no ADMIN no consulta la lista.
  if (rol !== 'ADMIN') {
    const r = validarReasignacion({ rol, motivo: '', destinoId: '', operadores: [] });
    return json({ error: /** @type {any} */ (r).error, codigo: /** @type {any} */ (r).codigo }, { status: 403 });
  }
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return json({ error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' },
      { status: 500 });
  }

  const cuerpo = await request.json().catch(() => ({}));
  let operadores;
  try {
    operadores = await operadoresDeLaOrg(cookies);
  } catch {
    return json({ error: 'No se pudo comprobar a quién se reasigna.' }, { status: 502 });
  }
  const validado = validarReasignacion({
    rol, motivo: cuerpo?.motivo, destinoId: cuerpo?.destino_usuario_id, operadores
  });
  if (!validado.ok) {
    const rechazo = /** @type {{ status: number, codigo: string, error: string }} */ (/** @type {any} */ (validado));
    return json({ error: rechazo.error, codigo: rechazo.codigo }, { status: rechazo.status });
  }
  const { destino, motivo } = /** @type {{ destino: { usuario_id: string, nombre: string }, motivo: string }} */ (
    /** @type {any} */ (validado));

  try {
    const resp = await fetch(`${baseUrl}/conversaciones/${params.id}/reasignar`, {
      method: 'POST',
      headers: headersMotor({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        tenant,
        ...autorDeSesion(locals),
        autor_rol: rol,
        destino_usuario_id: destino.usuario_id,
        destino_nombre: destino.nombre,
        motivo,
        clave_operacion: typeof cuerpo?.clave_operacion === 'string' ? cuerpo.clave_operacion : undefined
      })
    });
    const datos = await resp.json().catch(() => ({}));
    return json(datos, { status: resp.status });
  } catch (/** @type {any} */ err) {
    return json({ error: err?.message || 'No se pudo contactar al asistente' }, { status: 502 });
  }
}
