import { env } from '$env/dynamic/private';

/**
 * Server load: lista las conversaciones del asistente con clientes finales
 * (WhatsApp real y el simulador de prueba, distinguidos por `canal`), leyendo
 * directo del motor -- mismo patron que agentes/+page.server.js. Es una
 * bandeja de solo lectura: no hay acciones que POSTear desde acá.
 *
 * POR QUE ES UN LAYOUT Y NO UN PAGE
 * La bandeja es master-detail: la columna de la izquierda acompaña siempre,
 * tambien mientras se lee una conversacion. Si esta carga viviera en el page
 * del indice, entrar a /conversaciones/<id> la desmontaria y habria que
 * volver atras para elegir la siguiente. Como layout, SvelteKit la carga una
 * sola vez y la comparte con la pantalla hija.
 *
 * depends('app:conversaciones'): +layout.svelte sondea cada pocos segundos
 * mientras la pestaña esta visible y llama a invalidate('app:conversaciones')
 * -- asi un chat nuevo (o un mensaje que actualiza el ultimo_mensaje de la
 * lista) aparece solo, sin recargar la pagina. Sin este depends(),
 * invalidate() no tendria que re-ejecutar.
 *
 * @type {import('./$types').LayoutServerLoad}
 */
export async function load({ fetch, depends }) {
  depends('app:conversaciones');

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
