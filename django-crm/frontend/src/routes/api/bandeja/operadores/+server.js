import { json } from '@sveltejs/kit';
import { operadoresDeLaOrg, rolDeSesion } from '$lib/server/v2/operadores.js';

/**
 * Las personas activas de la organización, para el panel de carga del
 * supervisor (29/10/2026). Solo ADMIN: es a quién se le puede reasignar, y
 * reasignar es de ADMIN (contrato T4). Se pide al ABRIR el panel y no en el
 * load del layout, que se recarga cada 8 s.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, cookies }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  if (rolDeSesion(locals) !== 'ADMIN') {
    return json({ error: 'Solo un administrador ve la carga del equipo.' }, { status: 403 });
  }
  try {
    return json({ operadores: await operadoresDeLaOrg(cookies) });
  } catch {
    return json({ error: 'No se pudo leer el equipo.' }, { status: 502 });
  }
}
