import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

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
    const [respAgentes, respCatalogo, respEscalamiento] = await Promise.all([
      fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`, { headers: headersMotor() }),
      fetch(`${baseUrl}/agentes/catalogo?tenant=${encodeURIComponent(tenant)}`, { headers: headersMotor() }),
      // No bloquea la pantalla si falla -- ver por que abajo.
      fetch(`${baseUrl}/reportes/escalamiento?tenant=${encodeURIComponent(tenant)}&dias=14`, { headers: headersMotor() })
    ]);
    const datosAgentes = await respAgentes.json();
    const datosCatalogo = await respCatalogo.json();
    if (!respAgentes.ok) {
      return { agentes: [], catalogo: [], escalamiento: null, error: datosAgentes.error || 'No se pudo cargar la lista de agentes' };
    }
    // Mismo criterio que leerConfiguracionAsistente() en asistente-config.js:
    // esta metrica es un agregado, no el catalogo de agentes -- si el calculo
    // falla no tiene que tumbar la pantalla entera, se muestra sin el dato.
    const datosEscalamiento = respEscalamiento.ok ? await respEscalamiento.json() : null;
    return {
      agentes: datosAgentes.agentes,
      catalogo: respCatalogo.ok ? datosCatalogo.herramientas : [],
      escalamiento: datosEscalamiento
    };
  } catch (/** @type {any} */ err) {
    return { agentes: [], catalogo: [], escalamiento: null, error: err?.message || 'No se pudo contactar al asistente' };
  }
}
