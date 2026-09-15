/**
 * Las guías de sintonización de televisores.
 *
 * Desde el 10/09/2026 este catálogo es la FUENTE OFICIAL de esas
 * instrucciones. Antes el paso a paso vivía escrito en tres lugares — el
 * prompt del rol de soporte, la descripción de `activar_catv` en `tenants/`, y
 * la misma descripción copiada en `conectores/` — para algo que cambia por
 * marca de televisor y que nadie podía corregir sin un desarrollador.
 *
 * Mismo puente que `oferta.js` hacia crm-agentico — ver
 * `GET/POST /configuracion/guias-tv` en `nucleo/canales/api.py`.
 *
 * LAS REGLAS DE NEGOCIO NO ESTÁN ACÁ. Viven en `GuiaTV` y `TenantConfig`
 * (`nucleo/config/schema.py`) y las hace cumplir el motor al validar la config
 * entera antes de guardar. Esta pantalla ayuda a no equivocarse; el schema es
 * el que garantiza. Duplicarlas en JavaScript daría dos lugares donde
 * corregirlas y uno donde olvidarse.
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
 * @typedef {{
 *   marca: string,
 *   tipo_conexion: 'directo' | 'tdt',
 *   instrucciones: string,
 *   url_video: string,
 *   activa: boolean,
 *   observaciones: string
 * }} GuiaTV
 */

/**
 * El catálogo completo, activas y apagadas.
 *
 * A diferencia de lo que ve el agente, esto SÍ trae `observaciones`: son notas
 * de quien administra («confirmado con el técnico», «solo modelos posteriores
 * a 2019») y quien edita tiene que leerlas. La resolución que consume el
 * modelo nunca las entrega — ver `_ejecutar_consulta_guia_tv` en `motor.py`.
 *
 * @returns {Promise<{ guias_tv: GuiaTV[], tipos_conexion: string[] } | null>}
 */
export async function leerGuiasTV() {
  const cfg = destino();
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/guias-tv?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Reemplaza el catálogo entero — la pantalla manda su estado completo,
 * incluidas las apagadas. Apagar no es borrar: una guía que se retira porque
 * quedó vieja vuelve corregida, y borrarla pierde el texto que alguien
 * redactó.
 *
 * Si el motor rechaza el guardado (TDT con marca, activa sin instrucciones,
 * dos activas para la misma marca), el motivo vuelve tal cual para mostrarlo
 * en el formulario. No se traduce ni se resume: quien lo escribió explica
 * además por qué esa regla existe.
 *
 * @param {GuiaTV[]} guias
 */
export async function guardarGuiasTV(guias) {
  const cfg = destino();
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/configuracion/guias-tv`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, guias })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudieron guardar las guías.');
  return datos;
}
