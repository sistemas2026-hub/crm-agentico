/**
 * SmartOLT: prueba de conectividad de solo lectura contra el motor, antes de
 * guardar las credenciales como secreto. Las credenciales en si (guardar,
 * listar, borrar) reusan las funciones genericas de canal-whatsapp.js -- son
 * el mismo mecanismo de 'asistente.tenant_secrets' para cualquier nombre, no
 * algo especifico de WhatsApp pese al archivo en el que viven.
 *
 * Todavia no hay ninguna herramienta del catalogo que use estas credenciales
 * (ver nucleo/canales/api.py: POST /diagnostico/smartolt) -- esta pantalla
 * es el primer paso del sondeo, no una integracion terminada.
 */
import { env } from '$env/dynamic/private';

/**
 * @param {string} baseUrl
 * @param {string} apiKey
 * @returns {Promise<{ ok: boolean, detalle: string, muestra?: any[] }>}
 */
export async function probarConexionSmartolt(baseUrl, apiKey) {
  const motorUrl = env.PRIVATE_ASISTENTE_URL;
  if (!motorUrl) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL).');

  const resp = await fetch(`${motorUrl}/diagnostico/smartolt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo probar la conexion.');
  return datos;
}
