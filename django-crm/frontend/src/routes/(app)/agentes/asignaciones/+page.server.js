import { env } from '$env/dynamic/private';
import { getOrgPeopleAndTeams } from '$lib/server/v2/org-people.js';

/**
 * Quien puede usar cada agente. Cruza dos fuentes que viven en lados
 * distintos y no se conocen entre si:
 *
 *   las PERSONAS  salen del CRM (getOrgPeopleAndTeams -> /users/
 *                 get-teams-and-users/, ya filtrado a activos de esta
 *                 organizacion). El motor no lee las tablas del CRM.
 *   las ASIGNACIONES salen del motor (asistente.tenant_users), que es donde
 *                 vive lo nuestro.
 *
 * Solo lectura aca; guardar pasa por /api/agentes/asignaciones/<id>, con
 * gate de ADMIN propio -- no alcanza con esconder la pantalla.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ cookies, fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return {
      personas: [], asignaciones: {}, agentes: [],
      error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)'
    };
  }

  try {
    const [gente, resp] = await Promise.all([
      getOrgPeopleAndTeams(cookies),
      fetch(`${baseUrl}/agentes/asignaciones?tenant=${encodeURIComponent(tenant)}`)
    ]);
    const datos = await resp.json();
    if (!resp.ok) {
      return {
        personas: gente.people ?? [], asignaciones: {}, agentes: [],
        error: datos.error || 'No se pudieron leer las asignaciones'
      };
    }
    return {
      personas: gente.people ?? [],
      asignaciones: datos.asignaciones ?? {},
      agentes: datos.agentes ?? []
    };
  } catch (/** @type {any} */ err) {
    return {
      personas: [], asignaciones: {}, agentes: [],
      error: err?.message || 'No se pudo contactar al asistente'
    };
  }
}
