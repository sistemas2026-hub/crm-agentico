import { json } from '@sveltejs/kit';
import { getOrgPeopleAndTeams, resolveMe } from '$lib/server/v2/org-people.js';
import { leerAreas } from '$lib/server/v2/areas.js';

/**
 * El área de quien mira, para el filtro «Mi área» de la Bandeja (T22,
 * 30/10/2026). Se resuelve como en Tickets: la persona por su email en la
 * lista del equipo, y su área en las del motor. La sesión no trae el id del
 * perfil, así que no hay atajo.
 *
 * Aparte del load de la Bandeja a propósito: aquel se repite cada 8 s y esto
 * necesita la lista del equipo. La pantalla lo pide una vez.
 *
 * Sin área, `area: null`, y el filtro no aparece: no se inventa una.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, cookies, fetch }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }
  try {
    const [equipo, areas] = await Promise.all([
      getOrgPeopleAndTeams(cookies),
      leerAreas(locals, fetch)
    ]);
    const yo = resolveMe(equipo.people, /** @type {any} */ (locals).user?.email);
    return json({ area: (yo && areas.areaPorPersona?.[yo]) || null });
  } catch {
    return json({ area: null });
  }
}
