import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Server load: las propuestas pendientes (y ya resueltas, para el
 * historial) del asistente de configuracion guiada. Solo ADMIN -- un
 * miembro comun ni siquiera ve esta pantalla en el menu (Sidebar.svelte),
 * pero la carga tambien se protege aca por si alguien escribe la URL a
 * mano.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  if (locals.profile?.role !== 'ADMIN') {
    redirect(303, '/');
  }

  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return { propuestas: [], error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const resp = await fetch(`${baseUrl}/configuracion/propuestas?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return { propuestas: [], error: datos.error || 'No se pudieron cargar las propuestas' };
    }
    return { propuestas: datos.propuestas };
  } catch (/** @type {any} */ err) {
    return { propuestas: [], error: err?.message || 'No se pudo contactar al asistente' };
  }
}
