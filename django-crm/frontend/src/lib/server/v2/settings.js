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
 * sentinel; the reopen fetch throws a 403. Either way the hub still lists
 * those destinations for a member. It just omits the value and any warning it
 * cannot compute, the same way the shell omits the team badge a member cannot
 * count.
 *
 * Desde el 01/11/2026 NINGUNA lectura se espera ni se propaga: cada una viaja
 * como promesa, con plazo, y la que falla deja su fila sin valor y una linea
 * en el log. Ver getSettingsHub().
 */
import { conPlazo as conPlazoComun } from './plazo.js';
import { leerConfiguracionAsistente } from './asistente-config.js';
import { leerAjustesBandeja, leerRotulosBandeja } from './bandeja-config.js';
import { leerOrganizacion } from './organizacion-config.js';
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
 * endpoint is admin-only and throws 403). Any other error still propagates,
 * to conPlazo, which is the one that logs it.
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
 * @param {any} event
 */
export async function getSettingsHub(event) {
  //  LO DEL MOTOR VIAJA APARTE  --  26/10/2026
  //  ------------------------------------------
  //  Hasta ese dia las 21 lecturas iban en un solo Promise.all y la pagina no
  //  se dibujaba hasta que llegaba la ULTIMA. Ocho van al motor, que corre con
  //  un proceso y 8 hilos (docker-compose.prod.yml) y los comparte con los
  //  turnos de WhatsApp: con clientes escribiendo, esas ocho hacian fila detras
  //  de turnos de 10-30 s. Desde entonces salen como una promesa que SvelteKit
  //  manda cuando llega, cada una con su plazo (conPlazo).
  //
  //  Y LO DEL CRM TAMBIEN  --  01/11/2026
  //  -------------------------------------
  //  "La ventana configuracion demora para abrir o en ocasiones no abre." Las
  //  trece del CRM se seguian esperando juntas, sin plazo, y un error en
  //  CUALQUIERA tumbaba la pagina entera. Y son trece pedidos a la vez contra
  //  un backend que atiende doce (3 procesos x 4 hilos, entrypoint.sh)
  //  compartidos con la Bandeja de todos: con movimiento, hacian fila. Mientras
  //  tanto el clic no mostraba nada, porque SvelteKit no cambia de pantalla
  //  hasta que la carga termina.
  //
  //  Ahora la carga no espera NADA: cada lectura es una promesa propia en el
  //  primer nivel de lo que se devuelve (SvelteKit solo manda aparte las de
  //  ese nivel), la pagina se dibuja enseguida, y cada fila muestra su valor
  //  cuando llega el suyo -- una lenta no frena a las demas. La que falla o
  //  vence su plazo queda sin valor, como ya pasaba con lo que un miembro no
  //  puede ver, y deja una linea en el log diciendo cual fue.
  //  `resumir` corre DENTRO del plazo: si la respuesta no trae la forma
  //  esperada, esa fila queda sin valor con su linea en el log, igual que un
  //  error del backend -- nunca una promesa rechazada viajando al navegador.
  /**
   * @param {string} nombre @param {Promise<any>} lectura
   * @param {(v: any) => any} [resumir]
   */
  const crm = (nombre, lectura, resumir = (v) => v) =>
    conPlazo(
      Promise.resolve(lectura).then((v) => (v == null ? null : resumir(v))),
      PLAZO_CRM_MS,
      nombre
    );
  // Una sola lectura alimenta dos claves: no se pide dos veces.
  const aprobaciones = getApprovalRules(event);

  return {
    // El encabezado no espera: el nombre de la empresa viene en la sesion.
    orgNombre: event.locals?.org?.name ?? '',
    organizacion: crm('organizacion', getOrgSettings(event), (v) => v.org),
    calendar: crm('horario', getBusinessHours(event), (v) => v.calendar),
    // Admin-only oversight: null for a member (endpoint 403'd), so the hub
    // shows the destination without a value it is not allowed to compute.
    tokenTotals: crm('tokens', listOrgTokens(event), (v) => (v.forbidden ? null : v.totals)),
    peopleTotals: crm('equipo', listTeam(event), (v) => (v.forbidden ? null : v.totals)),
    routingTotals: crm('enrutamiento', getRoutingRules(event), (v) => v.totals),
    escalationTotals: crm('escalamiento', getEscalationPolicies(event), (v) =>
      escalationRollup(v.policies)
    ),
    mailboxTotals: crm('correo', getMailboxes(event), (v) => ({
      ...v.totals,
      silently_dropping: silentlyDropping(v.mailboxes, Date.now())
    })),
    reopen: crm('reapertura', reopenOrNull(getReopenPolicy(event))),
    approvalRules: crm('aprobaciones', aprobaciones, (v) => v.rules),
    approvalTotals: crm('aprobaciones', aprobaciones, (v) => v.totals),
    macroTotals: crm('macros', getMacros(event), (v) => v.totals),
    tagTotals: crm('etiquetas', getTags(event), (v) => v.totals),
    fieldTotals: crm('campos', getCustomFields(event), (v) => v.totals),
    // Cuantos canales de aviso hay. CERO no es un error --ninguna empresa nace
    // con esto configurado-- pero la tarjeta lo avisa, porque hoy esos avisos
    // los escribe alguien a mano. `leerAvisos` ya atrapa su propio error.
    avisosCampo: crm('avisos', leerAvisos(event), (v) => ({ cuantos: v.canales.length })),
    // Lo que sale del motor. Ver leerDelMotor().
    motor: leerDelMotor(event)
  };
}

/** Cuanto se espera cada lectura del CRM antes de dejar su fila sin valor. */
export const PLAZO_CRM_MS = 10000;

/** Cuanto se espera cada lectura del motor antes de dibujar la tarjeta sin valor. */
export const PLAZO_MOTOR_MS = 4000;

/**
 * `promesa`, o null si falla o tarda mas de `ms`. Nunca rechaza.
 *
 * El plazo corta la ESPERA de la pagina, no la llamada: el pedido sigue en
 * curso del otro lado hasta que conteste. Lo que se evita es que una tarjeta
 * deje a todas las demas mirando un servicio ocupado.
 *
 * Con `nombre`, la fila que queda sin valor lo deja dicho en el log: cual
 * lectura, y si fue el plazo o un error (su estado HTTP o su tipo). Texto
 * fijo, nunca el mensaje del error: un null que no deja rastro se ve igual
 * que una llamada mal escrita (ver settings-argumentos.test.js).
 *
 * Desde el 07/11/2026 es la de `plazo.js`, compartida con el menú y la
 * conversación; acá solo pone el plazo del motor por defecto y el prefijo
 * que dice de qué pantalla es la lectura.
 *
 * @template T
 * @param {Promise<T>} promesa
 * @param {number} [ms]
 * @param {string} [nombre]
 * @returns {Promise<T | null>}
 */
export function conPlazo(promesa, ms = PLAZO_MOTOR_MS, nombre) {
  return conPlazoComun(promesa, ms, nombre && `configuracion ${nombre}`);
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
    ajustesBandeja, rotulosBandeja, organizacion] = await Promise.all([
    conPlazo(leerConfiguracionAsistente(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerConfiguracionAsistente'),
    conPlazo(leerCanalWhatsapp(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerCanalWhatsapp'),
    conPlazo(leerSmartOlt(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerSmartOlt'),
    // Solo el conteo -- no pega contra WispHub (ver contarPlanesVenta()).
    conPlazo(contarPlanesVenta(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor contarPlanesVenta'),
    // Las dos listas salen de la config del tenant, que el motor ya tiene.
    conPlazo(leerOferta(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerOferta'),
    conPlazo(leerGuiasTV(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerGuiasTV'),
    // La lista de credenciales que hacen falta, y de las cargadas solo nombre
    // y pista. Nunca un valor.
    conPlazo(leerCredenciales(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerCredenciales'),
    // Dos enteros de la config del tenant. Sin definir NO lleva warn: es el
    // default deliberado, no una falta.
    conPlazo(leerAjustesBandeja(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerAjustesBandeja'),
    // Cuantas claves (motivos, etiquetas, casos) se muestran sin rotulo. Esta
    // SI avisa: es una palabra sin tilde en la cola de cada operador.
    conPlazo(leerRotulosBandeja(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerRotulosBandeja'),
    // La estructura de la empresa. Al hub le interesa UNA cosa: si esta
    // empresa ya declaro la suya o esta viendo la generica del producto. Las
    // dos se dibujan igual, asi que sin decirlo nadie lo sabria.
    conPlazo(leerOrganizacion(event.locals, event.fetch), PLAZO_MOTOR_MS, 'motor leerOrganizacion')
  ]);
  return {
    // null = no hay asistente, o no contesto a tiempo. El hub lista igual sus
    // destinos, sin valor, como ya hace con lo que un miembro no puede contar.
    asistente,
    canalWhatsapp,
    smartolt,
    ajustesBandeja,
    organizacion,
    // null = no se pudo leer; un numero = cuantas claves faltan rotular.
    sinRotulo: rotulosBandeja?.sin_rotulo
      ? Object.values(rotulosBandeja.sin_rotulo).reduce(
          (/** @type {number} */ n, /** @type {any} */ l) => n + (l?.length ?? 0), 0)
      : null,
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
