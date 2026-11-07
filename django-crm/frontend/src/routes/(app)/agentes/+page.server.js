import { fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { cambiarAutonomia, leerAutonomiaGanada } from '$lib/server/v2/capacidad.js';
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
    const [respAgentes, respCatalogo, respEscalamiento, respHuecos, ganada, supervisor] = await Promise.all([
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
      tareasDelSupervisor(cookies, locals)
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
      huecosPorRol,
      // La respuesta del motor ENTERA y sin renombrar (CLAUDE.md §6).
      autonomia: ganada.autonomia,
      errorAutonomia: ganada.error ?? null,
      esAdmin: locals.profile?.role === 'ADMIN',
      tareasSupervisor: supervisor
    };
  } catch (/** @type {any} */ err) {
    return { agentes: [], catalogo: [], escalamiento: null, huecosPorRol: {}, error: err?.message || 'No se pudo contactar al asistente' };
  }
}

const NOMBRE = /^[a-z0-9_]{1,64}$/;

/** Lo que el motor rechaza a proposito, dicho para quien decide (409, no 502). */
const RECHAZOS = /** @type {Record<string, string>} */ ({
  SIN_EVIDENCIA: 'Todavía no alcanza: mirá lo que le falta.',
  AGENTE_SIN_ESA_HERRAMIENTA: 'Este agente no usa esa herramienta.',
  YA_ES_AUTONOMA: 'Este agente ya la hace solo.',
  CONFIG_SIN_CONFIRMAR: 'No se pudo confirmar la configuración de la empresa desde la base. Probá de nuevo en un minuto.',
  NO_CANDIDATA: 'Esa acción no tiene en código las comprobaciones que hacen falta para hacerse sola.',
  NO_ES_UNA_ACCION_CON_APROBACION: 'Esa acción no pide aprobación: no hay nada que cambiar.'
});

/**
 * Que un agente haga sola una accion, o que vuelva a pedir aprobacion
 * (02/11/2026, PRD §2 y §8.18). Lo decide una persona ADMIN; el autor y su
 * rol salen de la SESION, nunca del navegador, y el motor los vuelve a exigir.
 * Sin 'rol' vale para todos los agentes que usan la herramienta.
 *
 * @type {import('./$types').Actions}
 */
export const actions = {
  async promover({ locals, fetch, request }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { autonomia: { error: 'Solo un administrador puede cambiar lo que un agente hace solo.' } });
    }
    const form = await request.formData();
    const accion = form.get('accion')?.toString().trim() ?? '';
    const rol = form.get('rol')?.toString().trim() ?? '';
    if (!NOMBRE.test(accion) || (rol && !NOMBRE.test(rol))) {
      return fail(400, { autonomia: { error: 'Esa acción o ese agente no se reconocen.' } });
    }
    if (form.get('confirmo') !== 'si') {
      return fail(400, { autonomia: { accion, rol, error: 'Marcá que entendés que la acción va a hacerse sola.' } });
    }
    try {
      await cambiarAutonomia(locals, fetch, 'promover', { accion, ...(rol ? { rol } : {}) });
    } catch (/** @type {any} */ e) {
      const conocido = RECHAZOS[e?.codigo];
      return fail(conocido ? 409 : 502,
        { autonomia: { accion, rol, error: conocido || e?.message || 'No se pudo cambiar.', faltan: e?.faltan ?? [] } });
    }
    return { autonomia: { accion, rol, ok: 'promovida' } };
  },

  async retirar({ locals, fetch, request }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, { autonomia: { error: 'Solo un administrador puede cambiar lo que un agente hace solo.' } });
    }
    const form = await request.formData();
    const accion = form.get('accion')?.toString().trim() ?? '';
    const rol = form.get('rol')?.toString().trim() ?? '';
    const motivo = form.get('motivo')?.toString().trim() ?? '';
    if (!NOMBRE.test(accion) || (rol && !NOMBRE.test(rol))) {
      return fail(400, { autonomia: { error: 'Esa acción o ese agente no se reconocen.' } });
    }
    if (!motivo) return fail(400, { autonomia: { accion, rol, error: 'Decí por qué vuelve a pedir aprobación.' } });
    try {
      await cambiarAutonomia(locals, fetch, 'retirar', { accion, motivo, ...(rol ? { rol } : {}) });
    } catch (/** @type {any} */ e) {
      return fail(502, { autonomia: { accion, rol, error: e?.message || 'No se pudo cambiar.' } });
    }
    return { autonomia: { accion, rol, ok: 'retirada' } };
  }
};
