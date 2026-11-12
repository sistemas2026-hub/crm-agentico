/**
 * Las fuentes de la portada "Hoy de la operacion", leidas en paralelo.
 *
 * Server-only. Junta lo que ya expone cada modulo -- ninguna llamada nueva al
 * backend --: la cola del CRM (/dashboard/today/), las conversaciones que
 * piden una persona y el estado de los agentes (motor), los bloqueos que
 * esperan al NOC, las instalaciones por decidir y los pedidos de bodega.
 *
 * CADA FUENTE FALLA SOLA
 * Una portada que desaparece porque una consulta fallo es peor que una que
 * dice que le falta un dato (mismo criterio que /centro-mando). Cada lectura
 * devuelve null si no pudo, y la cola se arma con las demas.
 *
 * Y no todas las fallas se anuncian. Las que cualquiera deberia poder leer
 * (conversaciones, el estado de Dexter, la cola del CRM) van a `noLeidas`, y
 * la pantalla las nombra. Las que dependen del rol -- inventario, bloqueos de
 * campo -- devuelven 403 a quien no tiene permiso todos los dias, y anunciarlo
 * seria ruido: simplemente no aparecen.
 *
 * El motor se consulta con un tiempo maximo: la portada es lo primero que se
 * abre, y un motor lento no puede dejarla en blanco.
 */
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { destinoDelAsistente } from '$lib/server/v2/tenant.js';
import { getToday } from '$lib/server/v2/today.js';
import { leerBandeja } from '$lib/server/v2/solicitudes.js';
import { leerBloqueosAbiertos } from '$lib/server/v2/programacion-noc.js';
import { leerReporte } from '$lib/server/v2/inventario.js';
import { leerTableroCapacidad } from '$lib/server/v2/capacidad.js';
import { contarTrabajoHumano } from '$lib/v2/hoy-operacion.js';

const ESPERA_MOTOR_MS = 5000;

/** GET al motor con tiempo maximo. Devuelve el JSON o lanza. */
async function delMotor(fetch, baseUrl, ruta) {
  const resp = await fetch(`${baseUrl}${ruta}`, {
    headers: headersMotor(),
    signal: AbortSignal.timeout(ESPERA_MOTOR_MS)
  });
  const datos = await resp.json();
  if (!resp.ok) throw new Error(datos?.error || `HTTP ${resp.status}`);
  return datos;
}

/**
 * @param {import('@sveltejs/kit').ServerLoadEvent} event
 */
export async function leerFuentesDeHoy(event) {
  const { cookies, locals, fetch } = event;
  // Sin motor o sin saber de que empresa es, no se le pide nada: no hay default.
  const destino = await destinoDelAsistente(locals, fetch);
  const q = destino ? `tenant=${encodeURIComponent(destino.tenant)}` : '';
  const sinMotor = () => Promise.reject(new Error('sin motor'));

  const [crm, conv, centro, solicitudes, bloqueos, pedidos] = await Promise.allSettled([
    getToday({ cookies }),
    // Mismo tope que la Bandeja (CERRADAS_DIAS): una cerrada hace mas de 30 dias no
    // puede estar en la cola de hoy, y sin el tope el motor recorre todo el historial.
    destino ? delMotor(fetch, destino.baseUrl, `/conversaciones?${q}&por_numero=1&cerradas_dias=30`) : sinMotor(),
    destino ? delMotor(fetch, destino.baseUrl, `/centro-mando?${q}&ventana=10`) : sinMotor(),
    leerBandeja(cookies),
    leerBloqueosAbiertos({ cookies }, { soloNoc: true }),
    leerReporte({ cookies }, 'pedidos')
  ]);

  const valor = (r) => (r.status === 'fulfilled' ? r.value : null);
  const crmV = valor(crm);
  const convV = valor(conv);
  const centroV = valor(centro);
  const solV = valor(solicitudes);
  const bloqV = valor(bloqueos);
  const pedV = valor(pedidos);

  // Lo que Hoy acaba de leer es exactamente lo que cuentan las insignias del
  // menú: se deja recordado, así la próxima navegación no vuelve a pedirlo.
  recordarInsignias(
    event,
    contarTrabajoHumano({
      conversaciones: convV?.conversaciones ?? null,
      bloqueos: deBloqueos(bloqV),
      solicitudes: deSolicitudes(solV)
    })
  );

  /** @type {string[]} */
  const noLeidas = [];
  if (!convV) noLeidas.push('las conversaciones');
  if (!centroV) noLeidas.push('el estado de Dexter');
  if (!crmV) noLeidas.push('tickets, facturas y tareas');

  return {
    crm: crmV,
    conversaciones: convV?.conversaciones ?? null,
    slaTomaMinutos: convV?.sla_toma_minutos ?? 0,
    centro: centroV,
    solicitudes: deSolicitudes(solV),
    bloqueos: deBloqueos(bloqV),
    pedidos: pedV && !pedV.error ? pedV.filas : null,
    noLeidas
  };
}

/** Lo que devolvió `leerBandeja`, o null si no se pudo leer. */
const deSolicitudes = (/** @type {any} */ v) => (v && !v.error ? v.solicitudes : null);
/** Lo que devolvió `leerBloqueosAbiertos`, o null si no se pudo leer. */
const deBloqueos = (/** @type {any} */ v) => (v && !v.error ? (v.datos?.bloqueos ?? []) : null);

/*
 * ═══════════════════════════════════════════════════════════════════════════
 *  LAS INSIGNIAS DEL MENÚ  --  12/11/2026
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Las insignias medían volumen del CRM (tickets abiertos, tareas) y no lo que
 * una persona tiene que hacer (auditoría del menú, Transversal). Ahora
 * Conversaciones, Supervisor NOC e Instalaciones cuentan lo mismo que «Por
 * área» de Hoy, con la misma función (`contarTrabajoHumano`).
 *
 * NO CUESTA UNA IDA AL MOTOR POR NAVEGACIÓN (PRD §8.21: la Bandeja era lenta
 * por contención, y cada lectura extra es un hilo del motor). La cola de
 * conversaciones es la consulta más cara de la portada, y el layout corre en
 * cada clic. Se recuerda por organización y rol durante INSIGNIAS_FRESCAS_MS:
 * con diez personas navegando, el motor ve una lectura cada 45 s, no una por
 * clic. Pasado eso y hasta INSIGNIAS_VIGENTES_MS se sigue mostrando la última
 * mientras se renueva por detrás (un número de hace un minuto en un menú
 * sirve; esperar a la cola en cada clic no). Las que llegan mientras otra está
 * en vuelo comparten su promesa. Y Hoy, que ya lee esas tres fuentes, deja su
 * resultado recordado.
 *
 * POR ORGANIZACIÓN Y ROL, no por organización sola: hoy las tres fuentes las
 * lee cualquier miembro, pero si mañana una se cierra por rol, la clave ya
 * impide que la insignia de un ADMIN le llegue a un USER.
 *
 * UNA FUENTE QUE FALLA NO TIENE INSIGNIA. Nunca un 0 inventado: sin clave, el
 * menú no dibuja nada.
 */
export const INSIGNIAS_FRESCAS_MS = 45 * 1000;
export const INSIGNIAS_VIGENTES_MS = 5 * 60 * 1000;
/** Los roles que abren el Supervisor NOC (campo/permissions.py::ROLES_GESTION). */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {Map<string, { valor: Record<string, number>, en: number, enVuelo?: Promise<Record<string, number>> }>} */
const _insignias = new Map();

/** Para las pruebas, que comparten el módulo. */
export function olvidarInsignias() {
  _insignias.clear();
}

/** @param {any} event @returns {string | null} */
function claveInsignias(event) {
  const org = event.locals?.org?.id;
  if (!org) return null;
  return `${org}|${event.locals?.profile?.role ?? 'USER'}`;
}

/** @param {any} event @param {Record<string, number>} valor */
function recordarInsignias(event, valor) {
  const clave = claveInsignias(event);
  if (!clave) return;
  // Hoy lee los bloqueos para todo rol; el menú solo los muestra a gestión.
  const propio = ROLES_GESTION.has(event.locals?.profile?.role)
    ? valor
    : Object.fromEntries(Object.entries(valor).filter(([k]) => k !== 'supervisor'));
  _insignias.set(clave, { valor: propio, en: Date.now(), enVuelo: _insignias.get(clave)?.enVuelo });
}

/** Las tres fuentes, leídas en paralelo; cada una falla sola. @param {any} event */
async function leerInsignias(event) {
  const { cookies, locals, fetch } = event;
  const destino = await destinoDelAsistente(locals, fetch);
  const conBloqueos = ROLES_GESTION.has(locals?.profile?.role);
  const [conv, sol, bloq] = await Promise.allSettled([
    destino
      ? delMotor(
          fetch,
          destino.baseUrl,
          `/conversaciones?tenant=${encodeURIComponent(destino.tenant)}&por_numero=1&cerradas_dias=30`
        )
      : Promise.reject(new Error('sin motor')),
    leerBandeja(cookies),
    conBloqueos ? leerBloqueosAbiertos({ cookies }, { soloNoc: true }) : Promise.resolve(null)
  ]);
  const valor = (/** @type {any} */ r) => (r.status === 'fulfilled' ? r.value : null);
  return contarTrabajoHumano({
    conversaciones: valor(conv)?.conversaciones ?? null,
    solicitudes: deSolicitudes(valor(sol)),
    bloqueos: deBloqueos(valor(bloq))
  });
}

/**
 * `{ conversaciones?, supervisor?, instalaciones? }` para el menú. Nunca
 * rechaza: sin organización, `{}`.
 *
 * @param {any} event
 * @returns {Promise<Record<string, number>>}
 */
export async function insigniasDeTrabajo(event) {
  const clave = claveInsignias(event);
  if (!clave) return {};
  const ahora = Date.now();
  const previo = _insignias.get(clave);
  if (previo && previo.en && ahora - previo.en < INSIGNIAS_FRESCAS_MS) return previo.valor;

  let enVuelo = previo?.enVuelo;
  if (!enVuelo) {
    enVuelo = leerInsignias(event)
      .catch(() => /** @type {Record<string, number>} */ ({}))
      .then((valor) => {
        _insignias.set(clave, { valor, en: Date.now() });
        return valor;
      });
    _insignias.set(clave, { valor: previo?.valor ?? {}, en: previo?.en ?? 0, enVuelo });
  }
  // La última conocida mientras se renueva, si todavía es de hace poco.
  if (previo && previo.en && ahora - previo.en < INSIGNIAS_VIGENTES_MS) return previo.valor;
  return enVuelo;
}

/*
 * «DEXTER RESOLVIÓ HOY»  --  12/11/2026
 *
 * La resolución sin persona de las últimas 24 h, SIEMPRE junto a sus dos
 * contrapesos (PRD §2, "Regla"): el recontacto y la satisfacción. Sola, la
 * primera premia cerrar sin resolver. Los números los calcula el motor
 * (`/reportes/capacidad`, nucleo/observabilidad/capacidad.py); acá no se suma
 * nada.
 *
 * Es «últimas 24 h» y no «desde la medianoche»: el motor mide por días hacia
 * atrás (mínimo 1). La tarjeta lo dice así.
 *
 * Se recuerda cinco minutos por organización: la portada se refresca sola cada
 * 45 s, y recalcular el tablero en cada vuelta sería pagarle al motor por un
 * número que no cambia a ese ritmo. Nunca rechaza: `null` = no se pudo leer.
 */
export const RESOLUCION_RECORDADA_MS = 5 * 60 * 1000;
/** @type {Map<string, { valor: any, en: number }>} */
const _resolucion = new Map();

/** Para las pruebas. */
export function olvidarResolucion() {
  _resolucion.clear();
}

/**
 * @param {any} event
 * @returns {Promise<null | { resueltas: number, cerradas: number, tasa: number | null,
 *   recontacto: { tasa: number | null, evaluadas: number, ventana_horas: number | null },
 *   satisfaccion: { promedio: number | null, respondidas: number } }>}
 */
export async function resolucionDelDia(event) {
  const org = event.locals?.org?.id;
  if (!org) return null;
  const previo = _resolucion.get(org);
  if (previo && Date.now() - previo.en < RESOLUCION_RECORDADA_MS) return previo.valor;
  try {
    const { tablero } = await leerTableroCapacidad(event.locals, event.fetch, 1);
    const r = tablero?.resolucion_sin_persona;
    const rc = tablero?.recontacto;
    const sa = tablero?.satisfaccion;
    // Sin los TRES no hay tarjeta: la palanca sin sus contrapesos no se muestra.
    if (!r || !rc || !sa) return null;
    const valor = {
      resueltas: r.resueltas ?? 0,
      cerradas: r.cerradas ?? 0,
      tasa: r.tasa ?? null,
      recontacto: {
        tasa: rc.tasa ?? null,
        evaluadas: rc.evaluadas ?? 0,
        ventana_horas: rc.ventana_horas ?? null
      },
      satisfaccion: { promedio: sa.promedio ?? null, respondidas: sa.respondidas ?? 0 }
    };
    _resolucion.set(org, { valor, en: Date.now() });
    return valor;
  } catch {
    return null;
  }
}
