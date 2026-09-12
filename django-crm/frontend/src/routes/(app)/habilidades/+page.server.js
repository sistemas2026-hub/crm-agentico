import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Habilidades: los procedimientos que cada agente puede cargar cuando le hacen
 * falta. Ver nucleo/habilidades/catalogo.py para qué son y en qué se
 * diferencian de un documento del corpus.
 *
 * Solo ADMIN, igual que /configuracion-guiada y por el mismo motivo: una
 * habilidad vigente es lo que un agente va a seguir "al pie de la letra"
 * frente a un cliente. El menú tampoco la muestra al resto, pero el gate va
 * también acá por si alguien escribe la URL a mano.
 *
 * Los huecos (qué le falta a cada agente) NO se cargan acá: recorren
 * conversaciones y pueden tardar. Se piden desde la página, cuando alguien los
 * pide — que una pantalla tarde en abrir es la forma más rápida de que nadie
 * la abra.
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
    return { habilidades: [], roles: [], error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  /** Los roles reales del tenant, para asignar sin escribirlos a mano. Un rol
   *  mal tipeado deja la habilidad aprobada y sin que nadie la vea. */
  let roles = [];
  try {
    const resp = await fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() });
    if (resp.ok) {
      const datos = await resp.json();
      roles = (datos.agentes ?? datos.roles ?? []).map(
        (/** @type {any} */ a) => (typeof a === 'string' ? a : a.nombre)).filter(Boolean);
    }
  } catch (/** @type {any} */ err) {
    console.error('[habilidades] no se pudieron leer los roles:', err?.message);
  }

  try {
    const resp = await fetch(`${baseUrl}/habilidades?tenant=${encodeURIComponent(tenant)}`,
      { headers: headersMotor() });
    const datos = await resp.json();
    if (!resp.ok) {
      return { habilidades: [], roles, error: datos.error || 'No se pudieron cargar.' };
    }
    return { habilidades: datos.habilidades ?? [], roles };
  } catch (/** @type {any} */ err) {
    console.error('[habilidades] motor inalcanzable:', err?.message);
    return { habilidades: [], roles, error: 'No se pudo contactar al asistente.' };
  }
}
