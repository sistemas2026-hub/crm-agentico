import { env } from '$env/dynamic/private';

/**
 * Server load: la lista fija de casos (tenant_config.manual.casos), todos
 * los ejemplos ya marcados (nucleo/canales/api.py:GET /manual/ejemplos) y los
 * documentos ya publicados en el corpus, para que la pantalla los agrupe por
 * caso. La lista de roles del tenant (roles_existentes, la misma que usa el
 * formulario de agentes) viaja tambien: es lo que arma los checkboxes de
 * "quien puede ver este documento" al subir uno nuevo o editar sus roles.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return {
      casos: [], ejemplos: [], documentos: [], revisiones: [], roles: [],
      error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)'
    };
  }

  try {
    const [respCasos, respEjemplos, respDocs, respRevisiones, respCatalogo] = await Promise.all([
      fetch(`${baseUrl}/manual/casos?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/manual/ejemplos?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/corpus/documentos?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/manual/revisiones?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/agentes/catalogo?tenant=${encodeURIComponent(tenant)}`)
    ]);
    const datosCasos = await respCasos.json();
    if (!respCasos.ok) {
      return {
        casos: [], ejemplos: [], documentos: [], revisiones: [], roles: [],
        error: datosCasos.error || 'No se pudo cargar la lista de casos'
      };
    }
    return {
      casos: datosCasos.casos,
      ejemplos: respEjemplos.ok ? (await respEjemplos.json()).ejemplos : [],
      documentos: respDocs.ok ? (await respDocs.json()).documentos : [],
      revisiones: respRevisiones.ok ? (await respRevisiones.json()).revisiones : [],
      roles: respCatalogo.ok ? (await respCatalogo.json()).roles_existentes : []
    };
  } catch (/** @type {any} */ err) {
    return {
      casos: [], ejemplos: [], documentos: [], revisiones: [], roles: [],
      error: err?.message || 'No se pudo contactar al asistente'
    };
  }
}
