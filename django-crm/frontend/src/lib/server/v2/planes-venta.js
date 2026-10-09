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
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * @typedef {{ nombre_wisphub: string, zonas: number[] }} PlanVenta
 * @typedef {{ id: number | string, nombre: string }} PlanCatalogo
 * @typedef {{ zona_id: number, zona_nombre: string, n_clientes: number }} ZonaConteo
 * @typedef {{ localidad: string, zonas: ZonaConteo[], n_clientes: number }} LocalidadZona
 * @typedef {{ plan_id: string, nombre: string, precio: string | null, bajada: string, descripcion: string }} PrecioDePlan
 * @typedef {{ nombre: string, descripcion: string }} HerramientaCandidata
 * @typedef {{ listado: string | null, detalle: string | null }} MarcasPrecio
 */

/**
 * Catalogo tecnico completo de WispHub EN VIVO (nunca cacheado -- quien
 * configura necesita ver el estado mas actual) mas la lista curada ya
 * guardada. Pega contra WispHub en cada llamada -- usar solo en la
 * pantalla dedicada, nunca en el hub de configuracion (ver
 * contarPlanesVenta() para eso).
 * @returns {Promise<{ catalogo: PlanCatalogo[], error_catalogo: string | null, planes_venta: PlanVenta[], localidades: LocalidadZona[], localidades_actualizado_en: string | null, precios_de_planes: PrecioDePlan[], precios_actualizado_en: string | null, herramientas: HerramientaCandidata[], marcas_precio: MarcasPrecio } | null>}
 */
export async function leerPlanesVenta(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
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
export async function contarPlanesVenta(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
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
export async function guardarPlanesVenta(locals, fetch, planes) {
  const cfg = await destinoDelAsistente(locals, fetch);
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

/**
 * Recorre el catalogo de clientes del proveedor entero y reemplaza el
 * catalogo localidad -> zona(s) real(es) -- ver
 * nucleo/herramientas/localidades.py. Puede tardar 60-90s (paginas
 * secuenciales contra WispHub): no se le pone un timeout corto a
 * proposito, cortarlo a mitad de camino no cancela el trabajo del lado
 * del motor, solo deja a quien mira la pantalla sin saber si termino.
 * @returns {Promise<{ localidades: LocalidadZona[], localidades_actualizado_en: string | null }>}
 */
/**
 * Sincroniza el PRECIO de cada plan.
 *
 * Son dos llamadas por plan del lado del motor —el listado da los ids, el
 * detalle da el precio— porque el proveedor los separó así: el listado
 * devuelve 50 planes y ningún precio. Con 50 planes eso son 50 consultas, y
 * por eso es una acción bajo demanda y nunca parte de una conversación.
 *
 * De que herramienta sale el listado y de cual el detalle es
 * configuracion por empresa, no un nombre fijo: se eligen en la pantalla y
 * el motor las guarda en el primer uso. Hasta el 07/10/2026 la unica via era
 * editar el YAML del tenant y cargarlo entero, y eso dejo el boton
 * devolviendo 400 en produccion.
 *
 * @param {any} locals
 * @param {typeof globalThis.fetch} fetch
 * @param {{ listado?: string, detalle?: string }} [marcas]
 */
export async function sincronizarPrecios(locals, fetch, marcas) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const cuerpo = { tenant: cfg.tenant };
  if (marcas?.listado && marcas?.detalle) {
    cuerpo.listado = marcas.listado;
    cuerpo.detalle = marcas.detalle;
  }

  const resp = await fetch(`${cfg.baseUrl}/configuracion/precios/sincronizar`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(cuerpo)
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    // El 400 de "falta elegir" NO es un fallo del proveedor: es la pantalla
    // que todavia no sabe de donde sacar los precios. Se distingue para que
    // pueda pedir las dos herramientas en vez de solo mostrar texto rojo.
    const e = /** @type {Error & { faltaElegir?: boolean, herramientas?: HerramientaCandidata[] }} */ (
      new Error(datos.error || 'No se pudieron sincronizar los precios.')
    );
    if (datos.falta_elegir) {
      e.faltaElegir = true;
      e.herramientas = datos.herramientas ?? [];
    }
    throw e;
  }
  return datos;
}

export async function sincronizarLocalidades(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/configuracion/localidades/sincronizar`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo sincronizar las localidades.');
  return datos;
}
