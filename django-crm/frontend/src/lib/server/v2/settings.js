/**
 * Settings hub: the wiring behind `/settings`.
 *
 * Server-only. The hub summarises every settings destination, so it needs a
 * number from each. Rather than a bespoke `/settings/summary/` endpoint, which
 * would have to reproduce, in Python across eight apps, the per-destination
 * rollups the pages already derive (escalation's "breaches going nowhere",
 * inbound's "silently dropping"). This fans out to the same server layers each
 * sub-page uses and assembles their totals. The calls run concurrently, so the
 * hub costs one round of parallel requests, not a dozen sequential ones.
 *
 * People, API tokens and the reopen policy are admin-only: their endpoints 403
 * a member. `listTeam` / `listOrgTokens` already fold that into a `forbidden`
 * sentinel; the reopen fetch throws, so it is caught below. Either way the hub
 * still lists those destinations for a member. It just omits the value and any
 * warning it cannot compute, the same way the shell omits the team badge a
 * member cannot count. Every other destination is readable by any member, so a
 * throw from one of those is a real failure and is left to propagate.
 */
import { leerConfiguracionAsistente } from './asistente-config.js';
import { leerAjustesBandeja } from './bandeja-config.js';
import { leerCanalWhatsapp } from './canal-whatsapp.js';
import { leerCredenciales } from './credenciales.js';
import { leerSmartOlt } from './smartolt.js';
import { leerAvisos } from './avisos-campo.js';
import { contarPlanesVenta } from './planes-venta.js';
import { leerOferta } from './oferta.js';
import { leerGuiasTV } from './guias-tv.js';
import { getBusinessHours } from './business-hours.js';
import { getCustomFields } from './custom-fields.js';
import { getEscalationPolicies } from './escalation.js';
import { getMailboxes } from './inbound-email.js';
import { getMacros } from './macros.js';
import { getOrgSettings } from './organization.js';
import { getReopenPolicy } from './reopen.js';
import { getRoutingRules } from './routing.js';
import { getTags } from './tags.js';
import { listTeam } from './team.js';
import { getApprovalRules } from './ticket-approvals.js';
import { listOrgTokens } from './tokens.js';

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

/**
 * Escalation "breaches that went nowhere", counted exactly as the escalation
 * page's `breachesGoingNowhere` does, so the hub's warning matches the page it
 * links to. A half is dead when the policy is off, reassigns to nobody, or
 * notifies nobody (no person and no team).
 * @param {any[]} policies
 */
function escalationRollup(policies) {
  let active = 0;
  let breaches = 0;
  for (const p of policies) {
    if (p.is_active) active += 1;
    /** @param {string} action @param {any} target */
    const halfDead = (action, target) => {
      if (!p.is_active) return true;
      if (action === 'reassign' && !target) return true;
      if (action === 'notify' && !target && !p.notify_team) return true;
      return false;
    };
    if (halfDead(p.first_response_action, p.first_response_target)) {
      breaches += p.breaches_last_30d?.first_response ?? 0;
    }
    if (halfDead(p.resolution_action, p.resolution_target)) {
      breaches += p.breaches_last_30d?.resolution ?? 0;
    }
  }
  return { active, count: policies.length, breaches_unhandled_30d: breaches };
}

/**
 * Mailboxes switched off that are still receiving mail, a customer ignored,
 * as opposed to an address deliberately retired. Matches the inbound page's
 * reasoning about which "off" is worth a warning.
 * @param {any[]} mailboxes @param {number} now
 */
function silentlyDropping(mailboxes, now) {
  return mailboxes.filter(
    (m) =>
      !m.is_active &&
      m.last_received_at &&
      now - new Date(m.last_received_at).getTime() < THIRTY_DAYS_MS
  ).length;
}

/**
 * Reopen policy → its `policy`, or null when the caller is a member (the
 * endpoint is admin-only and throws 403). Any other error still propagates.
 * @param {Promise<any>} promise
 */
async function reopenOrNull(promise) {
  try {
    return (await promise).policy;
  } catch (/** @type {any} */ err) {
    if (err?.status === 403) return null;
    throw err;
  }
}

/**
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 */
export async function getSettingsHub(event) {
  //  LO DEL MOTOR VIAJA APARTE  --  26/10/2026
  //  ------------------------------------------
  //  Hasta hoy las 21 lecturas iban en un solo Promise.all y la pagina no se
  //  dibujaba hasta que llegaba la ULTIMA. Ocho van al motor, que corre con un
  //  proceso y 8 hilos (docker-compose.prod.yml) y los comparte con los turnos
  //  de WhatsApp: con clientes escribiendo, esas ocho hacian fila detras de
  //  turnos de 10-30 s, y siete no tenian plazo. "Ya abrio pero demora", dijo
  //  el usuario.
  //
  //  Ahora lo del CRM se espera como antes, y lo del motor sale como una
  //  promesa que SvelteKit manda cuando llega: la pagina se dibuja sin
  //  esperarla, y cada tarjeta del asistente muestra su valor al llegar. Cada
  //  lectura del motor tiene ademas su plazo (conPlazo): si no contesta, esa
  //  tarjeta queda sin valor -- lo mismo que ya pasaba con el motor caido --,
  //  y la promesa nunca rechaza, asi que no hay error que tumbe la pagina.
  const motor = leerDelMotor(event);
  const [
    org,
    calendar,
    tokens,
    team,
    routing,
    escalation,
    mailbox,
    reopenPolicy,
    approval,
    macro,
    tag,
    field,
    avisosCampo
  ] = await Promise.all([
    getOrgSettings(event),
    getBusinessHours(event),
    listOrgTokens(event),
    listTeam(event),
    getRoutingRules(event),
    getEscalationPolicies(event),
    getMailboxes(event),
    reopenOrNull(getReopenPolicy(event)),
    getApprovalRules(event),
    getMacros(event),
    getTags(event),
    getCustomFields(event),
    // Cuantos canales de aviso tiene cargados esta empresa. Es del CRM, no del
    // motor. `leerAvisos` ya atrapa su propio error y devuelve la lista vacia:
    // el hub no se cae porque un destino no conteste.
    leerAvisos(event)
  ]);

  const now = Date.now();
  return {
    org: org.org,
    calendar: calendar.calendar,
    // Admin-only oversight: null for a member (endpoint 403'd), so the hub
    // shows the destination without a value it is not allowed to compute.
    tokenTotals: tokens.forbidden ? null : tokens.totals,
    peopleTotals: team.forbidden ? null : team.totals,
    routingTotals: routing.totals,
    escalationTotals: escalationRollup(escalation.policies),
    mailboxTotals: {
      ...mailbox.totals,
      silently_dropping: silentlyDropping(mailbox.mailboxes, now)
    },
    reopen: reopenPolicy,
    approvalRules: approval.rules,
    approvalTotals: approval.totals,
    macroTotals: macro.totals,
    tagTotals: tag.totals,
    fieldTotals: field.totals,
    // Cuantos canales hay. CERO no es un error --ninguna empresa nace con esto
    // configurado-- pero la tarjeta lo avisa, porque hoy esos avisos los
    // escribe alguien a mano.
    avisosCampo: { cuantos: avisosCampo.canales.length },
    // Lo que sale del motor, sin esperar. Ver leerDelMotor().
    motor
  };
}

/** Cuanto se espera cada lectura del motor antes de dibujar la tarjeta sin valor. */
export const PLAZO_MOTOR_MS = 4000;

/**
 * `promesa`, o null si falla o tarda mas de `ms`. Nunca rechaza.
 *
 * El plazo corta la ESPERA de la pagina, no la llamada: el pedido sigue en
 * curso del otro lado hasta que conteste. Lo que se evita es que una tarjeta
 * deje a todas las demas mirando un motor ocupado.
 *
 * @template T
 * @param {Promise<T>} promesa
 * @param {number} [ms]
 * @returns {Promise<T | null>}
 */
export function conPlazo(promesa, ms = PLAZO_MOTOR_MS) {
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let reloj;
  const vencido = new Promise((resolver) => {
    reloj = setTimeout(() => resolver(null), ms);
  });
  return Promise.race([Promise.resolve(promesa).catch(() => null), vencido]).finally(
    () => clearTimeout(reloj)
  );
}

/**
 * Las ocho lecturas que dependen del asistente, ya resumidas para el hub.
 *
 * LAS OCHO RECIBEN 'event.locals, event.fetch', Y HACE FALTA  --  07/10/2026.
 * Se las llamaba SIN argumentos: sin 'locals' no hay tenant, sin tenant no hay
 * destino, y cada una devolvia null por su propio catch. Faltaban las tarjetas
 * "Servicios y canales" y "Planes de venta", que dependen del rol 'ventas'.
 * El catch esta para que el motor caido no tumbe el hub; lo que no puede hacer
 * es tapar una llamada mal escrita. Ver settings-argumentos.test.js.
 *
 * @param {any} event
 */
async function leerDelMotor(event) {
  const [asistente, canalWhatsapp, smartolt, planesVenta, oferta, guiasTv, credenciales,
    ajustesBandeja] = await Promise.all([
    conPlazo(leerConfiguracionAsistente(event.locals, event.fetch)),
    conPlazo(leerCanalWhatsapp(event.locals, event.fetch)),
    conPlazo(leerSmartOlt(event.locals, event.fetch)),
    // Solo el conteo -- no pega contra WispHub (ver contarPlanesVenta()).
    conPlazo(contarPlanesVenta(event.locals, event.fetch)),
    // Las dos listas salen de la config del tenant, que el motor ya tiene.
    conPlazo(leerOferta(event.locals, event.fetch)),
    conPlazo(leerGuiasTV(event.locals, event.fetch)),
    // La lista de credenciales que hacen falta, y de las cargadas solo nombre
    // y pista. Nunca un valor.
    conPlazo(leerCredenciales(event.locals, event.fetch)),
    // Dos enteros de la config del tenant. Sin definir NO lleva warn: es el
    // default deliberado, no una falta.
    conPlazo(leerAjustesBandeja(event.locals, event.fetch))
  ]);
  return {
    // null = no hay asistente, o no contesto a tiempo. El hub lista igual sus
    // destinos, sin valor, como ya hace con lo que un miembro no puede contar.
    asistente,
    canalWhatsapp,
    smartolt,
    ajustesBandeja,
    // Cuantas pide el catalogo y cuantas estan cargadas. La fila del hub avisa
    // cuando falta alguna: eso es una herramienta que va a fallar al usarse.
    credencialesTotales: credenciales?.disponible
      ? {
          cargadas: credenciales.credenciales.filter((/** @type {any} */ c) => c.cargado).length,
          faltan: credenciales.credenciales.filter(
            (/** @type {any} */ c) => c.declarado && !c.cargado
          ).length
        }
      : null,
    planesVenta,
    oferta: oferta
      ? { servicios: (oferta.servicios_ofrecidos ?? []).filter((/** @type {any} */ s) => s.activo).length,
          canales: (oferta.parrilla_canales ?? []).length }
      : null,
    // Se cuentan las ACTIVAS y, aparte, si estan las dos de respaldo. Sin la
    // general, una marca sin guia propia deja al agente sin nada que
    // entregar; sin la de TDT, tampoco puede orientar a quien tiene cajita.
    guiasTv: guiasTv
      ? {
          activas: (guiasTv.guias_tv ?? []).filter((/** @type {any} */ g) => g.activa).length,
          tieneGeneral: (guiasTv.guias_tv ?? []).some(
            (/** @type {any} */ g) => g.activa && g.tipo_conexion === 'directo' && !(g.marca ?? '').trim()
          ),
          tieneTdt: (guiasTv.guias_tv ?? []).some(
            (/** @type {any} */ g) => g.activa && g.tipo_conexion === 'tdt'
          )
        }
      : null
  };
}
