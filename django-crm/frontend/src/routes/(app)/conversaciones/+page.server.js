import { env } from '$env/dynamic/private';

/**
 * Server load: lista las conversaciones del asistente con clientes finales
 * (WhatsApp real y el simulador de prueba, distinguidos por `canal`), leyendo
 * directo del motor -- mismo patron que agentes/+page.server.js. Es una
 * bandeja de solo lectura: no hay acciones que POSTear desde acá.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return {
      conversaciones: [],
      error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)'
    };
  }

  try {
    const resp = await fetch(`${baseUrl}/conversaciones?tenant=${encodeURIComponent(tenant)}`);
    const datos = await resp.json();
    if (!resp.ok) {
      return { conversaciones: [], error: datos.error || 'No se pudo cargar las conversaciones' };
    }
    return { conversaciones: datos.conversaciones };
  } catch (/** @type {any} */ err) {
    return { conversaciones: [], error: err?.message || 'No se pudo contactar al asistente' };
  }
}
