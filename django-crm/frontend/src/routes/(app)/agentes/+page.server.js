import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';

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
export async function load({ locals, fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return { agentes: [], catalogo: [], escalamiento: null, huecosPorRol: {}, error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const [respAgentes, respCatalogo, respEscalamiento, respHuecos] = await Promise.all([
      fetch(`${baseUrl}/agentes?tenant=${encodeURIComponent(tenant)}`, { headers: headersMotor() }),
      fetch(`${baseUrl}/agentes/catalogo?tenant=${encodeURIComponent(tenant)}`, { headers: headersMotor() }),
      // No bloquea la pantalla si falla -- ver por que abajo.
      fetch(`${baseUrl}/reportes/escalamiento?tenant=${encodeURIComponent(tenant)}&dias=14`, { headers: headersMotor() }),
      // QUE LE FALTA A CADA AGENTE, por rol (02/11/2026). Hasta hoy, al lado
      // de la tarjeta de un agente se mostraba la tasa de escalada de TODA la
      // empresa: 'db.tasa_escalamiento' dice en su propio docstring que "no
      // filtra por rol". Esto si es por rol, y es el mismo SQL determinista
      // que ya alimenta /habilidades -- no un segundo calculo de la misma
      // metrica, que es como dos definiciones empiezan a divergir.
      fetch(`${baseUrl}/habilidades/huecos?tenant=${encodeURIComponent(tenant)}&dias=14`, { headers: headersMotor() })
    ]);
    const datosAgentes = await respAgentes.json();
    const datosCatalogo = await respCatalogo.json();
    if (!respAgentes.ok) {
      return { agentes: [], catalogo: [], escalamiento: null, huecosPorRol: {}, error: datosAgentes.error || 'No se pudo cargar la lista de agentes' };
    }
    // Mismo criterio que leerConfiguracionAsistente() en asistente-config.js:
    // esta metrica es un agregado, no el catalogo de agentes -- si el calculo
    // falla no tiene que tumbar la pantalla entera, se muestra sin el dato.
    const datosEscalamiento = respEscalamiento.ok ? await respEscalamiento.json() : null;
    //  Mismo criterio: si el analisis falla, la pantalla se muestra sin el
    //  dato. Agrupado por rol aca y no en la tarjeta para que cada agente
    //  reciba lo suyo ya resuelto.
    const huecos = respHuecos.ok ? ((await respHuecos.json())?.huecos ?? []) : [];
    /** @type {Record<string, any[]>} */
    const huecosPorRol = {};
    for (const h of huecos) {
      if (!h?.rol) continue;
      (huecosPorRol[h.rol] ??= []).push(h);
    }
    return {
      agentes: datosAgentes.agentes,
      catalogo: respCatalogo.ok ? datosCatalogo.herramientas : [],
      escalamiento: datosEscalamiento,
      huecosPorRol
    };
  } catch (/** @type {any} */ err) {
    return { agentes: [], catalogo: [], escalamiento: null, huecosPorRol: {}, error: err?.message || 'No se pudo contactar al asistente' };
  }
}
