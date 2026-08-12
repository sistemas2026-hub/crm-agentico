import { env } from '$env/dynamic/private';

/**
 * Server load: la lista fija de casos (tenant_config.manual.casos) y todos
 * los ejemplos ya marcados (nucleo/canales/api.py:GET /manual/ejemplos),
 * para que la pantalla los agrupe por caso. Solo lectura -- marcar/
 * desmarcar pasa por Conversaciones o el Simulador, donde esta el contexto
 * completo de la respuesta (ver MarcarEjemplo.svelte).
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return { casos: [], ejemplos: [], error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const [respCasos, respEjemplos, respDocs] = await Promise.all([
      fetch(`${baseUrl}/manual/casos?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/manual/ejemplos?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/corpus/documentos?tenant=${encodeURIComponent(tenant)}`)
    ]);
    const datosCasos = await respCasos.json();
    if (!respCasos.ok) {
      return { casos: [], ejemplos: [], documentos: [], error: datosCasos.error || 'No se pudo cargar la lista de casos' };
    }
    return {
      casos: datosCasos.casos,
      ejemplos: respEjemplos.ok ? (await respEjemplos.json()).ejemplos : [],
      documentos: respDocs.ok ? (await respDocs.json()).documentos : []
    };
  } catch (/** @type {any} */ err) {
    return { casos: [], ejemplos: [], documentos: [], error: err?.message || 'No se pudo contactar al asistente' };
  }
}
