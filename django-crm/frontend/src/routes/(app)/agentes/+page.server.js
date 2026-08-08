import { env } from '$env/dynamic/private';

/**
 * Server load: lista los agentes configurados en el motor (crm-agentico), sus
 * herramientas (para el diagrama) y el catalogo de herramientas disponibles
 * (para el formulario de crear/editar, que vive en un Dialog aparte -- asi
 * no hace un viaje de red extra al abrirse). Los botones de crear/editar/
 * borrar POSTean/PUTean/DELETEan contra /api/agentes vía fetch del cliente
 * (mismo patron que /asistente y /simulador-whatsapp), esta funcion solo lee.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return { agentes: [], catalogo: [], error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const [respAgentes, respCatalogo] = await Promise.all([
      fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`),
      fetch(`${baseUrl}/agentes/catalogo?tenant=${encodeURIComponent(tenant)}`)
    ]);
    const datosAgentes = await respAgentes.json();
    const datosCatalogo = await respCatalogo.json();
    if (!respAgentes.ok) {
      return { agentes: [], catalogo: [], error: datosAgentes.error || 'No se pudo cargar la lista de agentes' };
    }
    return {
      agentes: datosAgentes.agentes,
      catalogo: respCatalogo.ok ? datosCatalogo.herramientas : []
    };
  } catch (/** @type {any} */ err) {
    return { agentes: [], catalogo: [], error: err?.message || 'No se pudo contactar al asistente' };
  }
}
