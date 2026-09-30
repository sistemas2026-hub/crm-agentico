import { json } from '@sveltejs/kit';
import {
  leerSeguimientoDeOrden,
  registrarSeguimiento
} from '$lib/server/v2/programacion-noc.js';

/**
 * La bitácora de una intervención: leerla, o agregarle un reporte.
 *
 * QUÉ NO HACE ESTA RUTA
 * ---------------------
 * No mueve el estado operativo de la orden. Registrar un BLOQUEO deja el hecho en
 * la bitácora y nada más: la máquina de estados vive en el backend y niega los
 * saltos inválidos. Que `bloqueada` sea un estado es la fase siguiente, con sus
 * transiciones declaradas. Ver SPEC/objetivos/seguimiento-campo-por-ticket.md.
 *
 * El gate de rol se repite acá además del que aplica el backend: dos capas, igual
 * que el resto del CRM. El aislamiento por empresa lo garantiza el backend con 404
 * estricto — nunca 403 — así que un UUID de otra empresa no se confirma.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @param {any} locals */
function rechazo(locals) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(locals.profile?.role)) {
    return json(
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver la bitácora.' },
      { status: 403 }
    );
  }
  return null;
}

/** @type {import('./$types').RequestHandler} */
export async function GET({ params, cookies, locals }) {
  const no = rechazo(locals);
  if (no) return no;

  const { datos, error } = await leerSeguimientoDeOrden({ cookies }, params.id);
  if (error) {
    return json({ error: error.mensaje, codigo: error.codigo }, { status: error.status ?? 502 });
  }
  return json(datos);
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ params, request, cookies, locals }) {
  const no = rechazo(locals);
  if (no) return no;

  const cuerpo = await request.json().catch(() => ({}));
  // La clave la manda quien reporta y se conserva tal cual: una nueva por intento
  // sería un identificador único, no una clave idempotente.
  const idempotencyKey = request.headers.get('Idempotency-Key') || cuerpo?.idempotency_key;

  const { datos, error } = await registrarSeguimiento({ cookies }, params.id, {
    momento: cuerpo?.momento,
    respuestas: cuerpo?.respuestas ?? {},
    idempotencyKey
  });

  if (error) {
    return json(
      { error: error.mensaje, codigo: error.codigo, campos: error.campos ?? null },
      { status: error.status ?? 502 }
    );
  }
  return json(datos, { status: 201 });
}
