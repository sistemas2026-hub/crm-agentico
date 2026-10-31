import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { tenantDeLaSesion } from '$lib/server/v2/tenant.js';
import { leerAreas } from '$lib/server/v2/areas.js';

/**
 * Lo que la oficina virtual necesita saber ANTES de dibujarse: quién existe.
 *
 * Dos cosas y nada más —el inventario de agentes y las áreas configuradas— y
 * las dos degradan: si el motor no responde, la sala se dibuja igual con el
 * puesto vacío y lo dice. Una pantalla de operación que desaparece cuando falla
 * una consulta es peor que una que admite que le falta un dato; es el mismo
 * criterio del centro de mando que ya está en producción.
 *
 * SOLO VIAJA LO QUE SE USA
 * El panorama del motor trae mucho más por agente —carga, conversaciones, qué
 * está haciendo—. Acá se recorta a tres campos: nombre, área y cargo. No es
 * ahorro de ancho de banda: es que lo que no llega al navegador no se puede
 * filtrar por accidente, y esta pantalla solo necesita saber quién se sienta
 * dónde. La actividad llega después por el flujo incremental, que ya tiene su
 * propia lista blanca.
 *
 * LA EMPRESA SALE DE LA SESIÓN
 * `tenantDeLaSesion`, en el servidor y nunca del cliente. Mismo patrón que el
 * resto: que el navegador pudiera elegir de qué empresa es la oficina
 * convertiría esta pantalla en un visor de operaciones ajenas.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return {
      agentes: [],
      areas: [],
      error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL o la empresa de la sesión)'
    };
  }

  const { areas } = await leerAreas(locals, fetch);

  try {
    const resp = await fetch(
      `${baseUrl}/centro-mando?tenant=${encodeURIComponent(tenant)}&ventana=10`,
      { headers: headersMotor() }
    );
    const datos = await resp.json();
    if (!resp.ok) {
      return {
        agentes: [],
        areas: areas.map((/** @type {any} */ a) => a?.nombre ?? a).filter(Boolean),
        error: datos.error || 'No se pudo leer el inventario de agentes'
      };
    }
    return {
      agentes: (datos.agentes || []).map((/** @type {any} */ a) => ({
        nombre: a.nombre,
        area: a.area ?? null,
        cargo: a.cargo ?? null,
        //  A quién atiende este agente. Viaja como INFORMACIÓN para la ficha,
        //  no como criterio de quién se sienta: medido el 30/10/2026, su valor
        //  por defecto en el esquema es `colaborador`, así que los tres roles
        //  que no lo declaran salen idénticos a los dos que sí. Separa 4 de 5,
        //  no distingue a un agente ejecutable de una capacidad asignada a una
        //  persona. Quién ocupa cada puesto se declara en la organización.
        orientado_a: a.orientado_a ?? null
      })),
      areas: areas.map((/** @type {any} */ a) => a?.nombre ?? a).filter(Boolean),
      error: null
    };
  } catch (/** @type {any} */ err) {
    return {
      agentes: [],
      areas: areas.map((/** @type {any} */ a) => a?.nombre ?? a).filter(Boolean),
      error: err?.message || 'No se pudo contactar al asistente'
    };
  }
}
