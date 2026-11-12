/**
 * El hilo del cliente: el ticket, su orden de campo y la ficha del cliente
 * (12/11/2026, auditoría del menú §1 puntos 1-2 y §4 ítems 5 y 6).
 *
 * Server-only. Todo lo que se muestra lo arma el backend
 * (`campo/hilo_del_cliente.py` y la ruta `/clientes/<servicio>/ficha` del
 * motor); esta capa solo junta las dos mitades y traduce los errores. No
 * recalcula nada: si una regla viviera acá y allá, una quedaría vieja.
 *
 * LA LECCIÓN QUE ESTA CAPA TIENE QUE RESPETAR (CLAUDE.md §6): `requiere_noc`
 * viajaba bien desde el backend y la capa servidor lo dejaba caer. Por eso acá
 * NO se copian campos a mano: se pasa lo que llegó, y las pruebas afirman sobre
 * lo que recibe la página.
 */
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';
import { headersMotor } from './motor-headers.js';
import { tenantDeLaSesion } from './tenant.js';
import { traducirError } from './supervisor-noc.js';
import { quienMira } from './ficha-visible.js';
import { getOrgPeopleAndTeams, resolveMe } from './org-people.js';
import { conPlazo } from './plazo.js';

/** El mismo criterio que `campo/hilo_del_cliente.py::SERVICIO_VALIDO`. */
export const SERVICIO_VALIDO = /^[A-Za-z0-9_-]{1,64}$/;
export const UUID_VALIDO = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
export const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/**
 * Las visitas de un ticket, para el bloque «Campo» del detalle.
 *
 * @param {{ cookies: any }} ctx
 * @param {string} casoId
 * @returns {Promise<{ datos: { ordenes: any[], servicio: string | null } | null, error: any }>}
 */
export async function leerOrdenesDelCaso(ctx, casoId) {
  if (!UUID_VALIDO.test(String(casoId ?? ''))) {
    return { datos: null, error: { codigo: 'NO_ENCONTRADA', status: 404, mensaje: 'Ese ticket no existe.' } };
  }
  try {
    const d = await apiRequest(`/campo/casos/${casoId}/ordenes/`, {}, ctx);
    return {
      datos: { ordenes: Array.isArray(d?.ordenes) ? d.ordenes : [], servicio: d?.servicio ?? null },
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'las visitas de este ticket') };
  }
}

/**
 * De qué ticket y servicio es una orden, quién va y sus evidencias. Sin
 * teléfono ni GPS: no salen del backend.
 *
 * @param {{ cookies: any }} ctx
 * @param {string} ordenId
 */
export async function leerHiloDeOrden(ctx, ordenId) {
  if (!UUID_VALIDO.test(String(ordenId ?? ''))) {
    return { datos: null, error: { codigo: 'NO_ENCONTRADA', status: 404, mensaje: 'Esa orden no existe.' } };
  }
  try {
    return { datos: await apiRequest(`/campo/trabajos/${ordenId}/hilo/`, {}, ctx), error: null };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'esta orden de trabajo') };
  }
}

/**
 * La conversación que originó un caso, solo su id, para enlazarla. La misma
 * ruta del motor que usa el detalle del ticket; sin `servicio`, así no arma
 * la ficha técnica (que acá no se muestra). Null si no hay o no se pudo.
 *
 * @param {any} locals
 * @param {typeof fetch} fetch
 * @param {string | null} casoId
 */
export async function conversacionDelCaso(locals, fetch, casoId) {
  if (!casoId || !UUID_VALIDO.test(casoId)) return null;
  try {
    const base = env.PRIVATE_ASISTENTE_URL;
    if (!base) return null;
    const tenant = await tenantDeLaSesion(locals, fetch);
    if (!tenant) return null;
    const r = await fetch(
      `${base}/conversaciones/por-caso/${casoId}?${new URLSearchParams({ tenant })}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(10000) }
    );
    if (!r.ok) return null;
    const d = await r.json();
    return d?.conversacion?.id ? String(d.conversacion.id) : null;
  } catch {
    return null;
  }
}

/**
 * La ficha del cliente por su servicio: lo que sabe el CRM (tickets, órdenes,
 * solicitudes) y lo que sabe el motor (conversaciones, estado del servicio y
 * del equipo). Las dos mitades se piden en paralelo y cada una falla sola:
 * sin el motor, la ficha se muestra con lo del CRM y lo dice.
 *
 * El rol y el perfil viajan al motor para que recorte la ficha de la persona
 * con su criterio por área (`nucleo/seguridad/ficha_por_area.py`): el
 * criterio es uno y vive allá.
 *
 * @param {{ cookies: any, locals: any, fetch: typeof fetch }} ctx
 * @param {string} servicio
 */
export async function leerFichaDelCliente({ cookies, locals, fetch }, servicio) {
  if (!SERVICIO_VALIDO.test(String(servicio ?? ''))) {
    return {
      crm: null,
      motor: null,
      error: { codigo: 'NO_ENCONTRADA', status: 404, mensaje: 'Ese servicio no es válido.' }
    };
  }
  const delCrm = apiRequest(`/campo/clientes/${encodeURIComponent(servicio)}/`, {}, { cookies })
    .then((/** @type {any} */ d) => ({ datos: d, error: null }))
    .catch((/** @type {any} */ err) => ({ datos: null, error: traducirError(err, 'la ficha de este cliente') }));

  const delMotor = (async () => {
    try {
      const base = env.PRIVATE_ASISTENTE_URL;
      const tenant = await tenantDeLaSesion(locals, fetch);
      if (!base || !tenant) return null;
      // Quién mira, con el MISMO criterio que la Bandeja y el ticket
      // (12/11/2026): el rol del JWT verificado y el Profile.id buscado por
      // correo, porque `locals.profile` no trae id. Si el CRM no contesta a
      // tiempo, sin perfil: el motor cae al defecto, que es el lado seguro.
      const perfil = await conPlazo(
        getOrgPeopleAndTeams(cookies).then((g) => resolveMe(g.people, locals?.user?.email)),
        5000,
        'ficha del cliente perfil de quien mira'
      ).catch(() => null);
      const q = new URLSearchParams({ tenant, ...quienMira(locals, perfil) });
      const r = await fetch(`${base}/clientes/${encodeURIComponent(servicio)}/ficha?${q}`, {
        headers: headersMotor(),
        signal: AbortSignal.timeout(20000)
      });
      return r.ok ? await r.json() : null;
    } catch {
      return null;
    }
  })();

  const [crm, motor] = await Promise.all([delCrm, delMotor]);
  return { crm: crm.datos, motor, error: crm.error };
}
