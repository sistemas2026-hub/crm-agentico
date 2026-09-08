/**
 * La oferta de la empresa: que servicios vende, y que canales trae la TV.
 *
 * Nace de una falla medida el 08/09/2026 en el simulador. Un prospecto pidio
 * telefonia fija y el agente contesto, tres veces seguidas, "solo tenemos
 * planes de internet residencial y combos con television" -- sin llamar a
 * ninguna herramienta, porque no tenia ninguna que se lo dijera. La respuesta
 * era correcta y no tenia fuente: acerto porque un ISP obviamente vende
 * internet. Con otro servicio, o en otro tenant, esa misma frase le niega al
 * cliente algo que la empresa si vende.
 *
 * Esta pantalla es donde ese dato deja de ser una adivinanza.
 *
 * Mismo puente que planes-venta.js hacia crm-agentico -- ver
 * GET /configuracion/oferta y los POST en nucleo/canales/api.py.
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
 * @typedef {{ nombre: string, activo: boolean, descripcion: string }} ServicioOfrecido
 */

/**
 * Lo que hay cargado hoy. Sin red hacia terceros: las dos listas salen de la
 * config del tenant, que el motor ya tiene en memoria.
 * @returns {Promise<{ servicios_ofrecidos: ServicioOfrecido[], parrilla_canales: string[] } | null>}
 */
export async function leerOferta() {
  const cfg = destino();
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/oferta?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Reemplaza la lista entera -- la pantalla manda su estado completo,
 * incluidos los servicios apagados. Apagar no es borrar: un servicio que se
 * deja de vender vuelve, y borrarlo pierde su descripcion.
 * @param {ServicioOfrecido[]} servicios
 */
export async function guardarServicios(servicios) {
  const cfg = destino();
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/configuracion/servicios`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, servicios })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudieron guardar los servicios.');
  return datos;
}

/**
 * Sube el Excel de la parrilla. Se manda tal cual llego, sin parsearlo aca:
 * quien lo entiende es el motor (openpyxl), y duplicar el criterio de
 * deduplicacion en dos lenguajes es garantizar que se separen.
 *
 * Devuelve tambien los DESCARTADOS por duplicados -- sin eso, quien sube el
 * archivo cree que cargo mas canales de los que cargo.
 * @param {File} archivo
 * @returns {Promise<{ parrilla_canales: string[], descartados: string[], total: number }>}
 */
export async function subirParrilla(archivo) {
  const cfg = destino();
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const cuerpo = new FormData();
  cuerpo.append('tenant', cfg.tenant);
  cuerpo.append('archivo', archivo);

  // Sin 'Content-Type' a mano: fetch le pone el boundary del multipart, y
  // fijarlo nosotros lo rompe sin dar un error que se entienda.
  const resp = await fetch(`${cfg.baseUrl}/configuracion/parrilla`, {
    method: 'POST',
    headers: headersMotor(),
    body: cuerpo
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo cargar la parrilla.');
  return datos;
}
