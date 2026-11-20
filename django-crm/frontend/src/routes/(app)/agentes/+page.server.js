import { env } from '$env/dynamic/private';
import { leerAutonomiaGanada } from '$lib/server/v2/capacidad.js';
import { accionesDeAutonomia } from '$lib/server/v2/acciones-autonomia.js';
import { leerDesempeno } from '$lib/server/v2/agentes.js';
import { leerAjustes } from '$lib/server/v2/ajustes-supervisor.js';
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
/** Quien puede ver las tareas del Supervisor: el mismo conjunto que su pantalla de Ajustes. */
const VEN_EL_SUPERVISOR = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/**
 * Que tareas hace solo el Supervisor NOC (02/11/2026): se VEN aca, junto a lo
 * que hace solo cada agente, y se cambian en Supervisor NOC -> Ajustes, que
 * tiene sus propios permisos (tambien el Jefe de Operaciones, no solo ADMIN).
 * Nunca rechaza: si no se puede leer, la tarjeta se ve sin el dato.
 * @param {any} cookies @param {any} locals
 */
async function tareasDelSupervisor(cookies, locals) {
  if (!VEN_EL_SUPERVISOR.has(locals?.profile?.role)) return null;
  try {
    const ajustes = /** @type {any} */ (await leerAjustes({ cookies }));
    const tareas = Array.isArray(ajustes?.tareas) ? ajustes.tareas : null;
    return tareas && { delegadas: tareas.filter((/** @type {any} */ t) => t.delegada).map(
      (/** @type {any} */ t) => t.nombre), total: tareas.length };
  } catch {
    return null;
  }
}

export async function load({ locals, fetch, cookies }) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = await tenantDeLaSesion(locals, fetch);
  if (!baseUrl || !tenant) {
    return { agentes: [], catalogo: [], escalamiento: null, huecosPorRol: {}, error: 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT)' };
  }

  try {
    const [respAgentes, respCatalogo, respEscalamiento, respHuecos, ganada, supervisor, desempeno] = await Promise.all([
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
      fetch(`${baseUrl}/habilidades/huecos?tenant=${encodeURIComponent(tenant)}&dias=14`, { headers: headersMotor() }),
      //  QUE HACE SOLO CADA AGENTE (02/11/2026). Vivia en /capacidad, para
      //  toda la empresa; el usuario: "eso deberia ir en cada agente". Nunca
      //  rechaza (devuelve el error): si no se calcula, los agentes se ven
      //  igual, sin el estado de su autonomia.
      leerAutonomiaGanada(locals, fetch).catch(() => ({ autonomia: null, error: 'No se pudo leer lo que hace solo cada agente.' })),
      tareasDelSupervisor(cookies, locals),
      //  Escaladas POR AGENTE (13/11/2026), para la columna de la lista. Nunca
      //  rechaza: sin el dato, la columna dice un guion.
      leerDesempeno({ baseUrl, tenant }, fetch, 30)
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
      //  Por que motivos puede pasar a una persona un agente, con su rotulo
      //  (04/11/2026). Los elige el formulario, paso "Que hace".
      motivosEscalada: respCatalogo.ok ? (datosCatalogo.motivos_escalada ?? []) : [],
      escalamiento: datosEscalamiento,
      huecosPorRol,
      // La respuesta del motor ENTERA y sin renombrar (CLAUDE.md §6).
      autonomia: ganada.autonomia,
      errorAutonomia: ganada.error ?? null,
      esAdmin: locals.profile?.role === 'ADMIN',
      tareasSupervisor: supervisor,
      desempeno: desempeno ?? null
    };
  } catch (/** @type {any} */ err) {
    return { agentes: [], catalogo: [], escalamiento: null, huecosPorRol: {}, error: err?.message || 'No se pudo contactar al asistente' };
  }
}

/**
 * Que un agente haga sola una accion, o que vuelva a pedir aprobacion. La
 * implementacion es UNA, compartida con la pagina de cada agente: ver
 * $lib/server/v2/acciones-autonomia.js.
 *
 * @type {import('./$types').Actions}
 */
export const actions = { ...accionesDeAutonomia };
