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
    destino ? delMotor(fetch, destino.baseUrl, `/conversaciones?${q}&por_numero=1`) : sinMotor(),
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
    solicitudes: solV && !solV.error ? solV.solicitudes : null,
    bloqueos: bloqV && !bloqV.error ? (bloqV.datos?.bloqueos ?? []) : null,
    pedidos: pedV && !pedV.error ? pedV.filas : null,
    noLeidas
  };
}
