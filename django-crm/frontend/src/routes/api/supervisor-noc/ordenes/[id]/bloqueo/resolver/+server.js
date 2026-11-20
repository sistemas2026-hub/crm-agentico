import { json } from '@sveltejs/kit';
import { resolverBloqueo } from '$lib/server/v2/programacion-noc.js';

/**
 * Destraba un trabajo detenido.
 *
 * El estado al que vuelve lo guardó el bloqueo al abrirse; esta ruta no lo elige.
 * `volver_a` se manda solo cuando alguien quiere otro destino porque el mundo
 * cambió mientras el trabajo estaba trabado, y el backend lo valida contra la
 * máquina de transiciones igual que cualquier otro movimiento de estado.
 *
 * Idempotente por `Idempotency-Key`: destrabar dos veces por un reintento de red
 * dejaría dos eventos y una historia que cuenta dos resoluciones donde hubo una.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').RequestHandler} */
export async function POST({ params, request, cookies, locals }) {
  if (!locals.user) {
    return json({ error: 'Tu sesión expiró. Volvé a iniciar sesión.' }, { status: 401 });
  }
  if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
    return json(
      { error: 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede resolver un bloqueo.' },
      { status: 403 }
    );
  }

  const cuerpo = await request.json().catch(() => ({}));
  const { datos, error } = await resolverBloqueo({ cookies }, params.id, {
    queSeHizo: cuerpo?.que_se_hizo ?? '',
    rol: cuerpo?.resuelto_por_rol ?? '',
    volverA: cuerpo?.volver_a ?? undefined,
    idempotencyKey: request.headers.get('Idempotency-Key') ?? cuerpo?.idempotency_key
  });

  if (error) {
    return json(
      { error: error.mensaje, codigo: error.codigo, campos: error.campos ?? null },
      { status: error.status ?? 502 }
    );
  }
  return json(datos);
}
