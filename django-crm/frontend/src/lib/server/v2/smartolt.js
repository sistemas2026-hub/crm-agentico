/**
 * SmartOLT: la API key que reinicia y consulta las ONUs de la OLT, y el
 * subdominio contra el que apunta (varia por empresa -- Rapilink no es la
 * unica que se va a conectar). Mismo puente que canal-whatsapp.js hacia
 * crm-agentico -- comparte el mismo endpoint /configuracion/canales (ver la
 * nota en nucleo/canales/api.py sobre por que SmartOLT vive ahi sin ser un
 * canal de contacto).
 *
 * El subdominio SI se guarda desde esta pantalla, pero NO como secreto: usa
 * /configuracion/variables (generico, texto plano) en vez de /secretos
 * (cifrado) -- un subdominio no es una credencial, y cifrarlo no aportaria
 * nada. Ver TenantConfig.variables_tenant / Herramienta.base_url_ref en
 * nucleo/config/schema.py.
 */
import { env } from '$env/dynamic/private';
import { headersMotor } from './motor-headers.js';

const REF_API_KEY = 'SMARTOLT_API_KEY';

function destino() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) return null;
  return { baseUrl, tenant };
}

/**
 * Estado de la integracion: si el catalogo del tenant tiene las herramientas
 * de SmartOLT instaladas, contra que subdominio estan apuntando (y el NOMBRE
 * de esa variable, para poder guardarla), y si la clave ya esta cargada --
 * esto ultimo sale de /secretos aparte (mismo endpoint generico que usa
 * WhatsApp), asi que esta funcion hace las dos llamadas para que el hub de
 * ajustes no tenga que saber de la segunda.
 * @returns {Promise<{ instalado: boolean, subdominio: string | null, subdominio_ref: string | null, ref_clave: string, tiene_clave: boolean } | null>}
 */
export async function leerSmartOlt() {
  const cfg = destino();
  if (!cfg) return null;
  try {
    const [respCanal, respSecretos] = await Promise.all([
      fetch(`${cfg.baseUrl}/configuracion/canales?tenant=${encodeURIComponent(cfg.tenant)}`,
        { headers: headersMotor() }),
      fetch(`${cfg.baseUrl}/secretos?tenant=${encodeURIComponent(cfg.tenant)}`,
        { headers: headersMotor() })
    ]);
    if (!respCanal.ok) return null;
    const datos = await respCanal.json();
    const smartolt = datos.smartolt ?? null;
    if (!smartolt) return null;

    const secretosDatos = respSecretos.ok ? await respSecretos.json() : { secretos: [] };
    const secretos = secretosDatos.secretos ?? [];
    return {
      ...smartolt,
      tiene_clave: secretos.some((/** @type {any} */ s) => s.nombre === REF_API_KEY)
    };
  } catch {
    return null;
  }
}

/**
 * Guarda una variable de tenant NO secreta (ej. el subdominio de SmartOLT).
 * Generico: sirve para cualquier 'base_url_ref' futuro, no solo SmartOLT.
 * @param {string} nombre
 * @param {string} valor
 */
export async function guardarVariable(nombre, valor) {
  const cfg = destino();
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/configuracion/variables/${encodeURIComponent(nombre)}`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, valor })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo guardar la variable.');
  return datos;
}

/**
 * Prueba de conectividad de solo lectura contra SmartOLT, con lo que la
 * persona tiene ESCRITO en pantalla en ese momento -- no lo ya guardado --
 * para poder corregir un dato mal pegado sin round-trip de guardar primero.
 * Ver POST /diagnostico/smartolt en nucleo/canales/api.py.
 * @param {string} subdominio
 * @param {string} apiKey
 * @returns {Promise<{ ok: boolean, detalle: string }>}
 */
export async function probarConexion(subdominio, apiKey) {
  const cfg = destino();
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/diagnostico/smartolt`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ base_url: subdominio, api_key: apiKey })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo probar la conexión.');
  return datos;
}

export { REF_API_KEY };
