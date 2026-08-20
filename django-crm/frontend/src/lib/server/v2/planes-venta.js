/**
 * Planes de venta: la lista CURADA de planes que el agente 'ventas' ofrece
 * a un prospecto nuevo, distinta del catalogo TECNICO completo de WispHub
 * (que trae variantes duplicadas y nombres legacy pensados para facturar
 * clientes existentes, no para vender). Nace de un caso real: un prospecto
 * pregunto por "300 megas" y el catalogo tecnico devolvio tres resultados
 * distintos con ese numero -- cual es el que de verdad se vende es una
 * decision humana, esta pantalla es donde se toma.
 *
 * Mismo puente que smartolt.js hacia crm-agentico -- ver
 * GET/PUT /configuracion/planes-venta en nucleo/canales/api.py.
 */
import { env } from '$env/dynamic/private';
import { headersMotor } from './motor-headers.js';

function destino() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/**
 * @typedef {{ nombre_wisphub: string, localidades: string[] }} PlanVenta
 * @typedef {{ id: number | string, nombre: string }} PlanCatalogo
 */

/**
 * Catalogo tecnico completo de WispHub EN VIVO (nunca cacheado -- quien
 * configura necesita ver el estado mas actual) mas la lista curada ya
 * guardada. Pega contra WispHub en cada llamada -- usar solo en la
 * pantalla dedicada, nunca en el hub de configuracion (ver
 * contarPlanesVenta() para eso).
 * @returns {Promise<{ catalogo: PlanCatalogo[], error_catalogo: string | null, planes_venta: PlanVenta[] } | null>}
 */
export async function leerPlanesVenta() {
  const cfg = destino();
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/planes-venta?tenant=${encodeURIComponent(cfg.tenant)}&catalogo=1`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Solo el conteo de planes ya curados -- sin pedir '?catalogo=1', no le
 * pega a WispHub. Para el hub de /settings, que no necesita el catalogo
 * completo, solo saber "cuantos hay" para el resumen de la fila.
 * @returns {Promise<{ cantidad: number } | null>}
 */
export async function contarPlanesVenta() {
  const cfg = destino();
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/planes-venta?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    const datos = await resp.json();
    return { cantidad: (datos.planes_venta ?? []).length };
  } catch {
    return null;
  }
}

/**
 * Reemplaza entera la lista curada -- se manda el estado completo de la
 * pantalla (todo lo que quedo tildado, con sus localidades), no un delta.
 * @param {PlanVenta[]} planes
 */
export async function guardarPlanesVenta(planes) {
  const cfg = destino();
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/configuracion/planes-venta`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, planes })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo guardar la lista de planes.');
  return datos;
}
