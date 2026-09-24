/**
 * Los dos números con los que la Bandeja emite un veredicto.
 *
 * Server-only, mismo puente que `asistente-config.js`: habla con el motor
 * (`PRIVATE_ASISTENTE_URL`), no con Django, y el tenant sale del entorno del
 * servidor -- nunca del cliente. Quien abre la pantalla no elige de qué
 * empresa es la configuración que va a leer o escribir.
 *
 * POR QUE ESTOS DOS Y NO UNO SOLO
 * -------------------------------
 * Los dos comparten una propiedad que no es obvia: **admiten "sin definir", y
 * eso no es un hueco**. `sla_toma_minutos = 0` y `umbral_rx_dbm = null`
 * significan que la empresa todavía no decidió el valor, y entonces la Bandeja
 * muestra el dato crudo sin afirmar si está bien o mal. Es deliberado: un
 * umbral inventado convierte una lectura correcta en un veredicto falso, y en
 * óptica el valor correcto depende del despliegue de cada ISP.
 *
 * Por eso viven juntos en una pantalla: la pregunta que contestan es la misma
 * --"¿qué puede afirmar la Bandeja?"-- y la respuesta por defecto de los dos
 * es "nada, todavía".
 *
 * POR QUE `leer` NO LANZA
 * -----------------------
 * Mismo motivo que el resto de este archivo hermano: el hub de `/settings`
 * hace un `Promise.all` de una docena de cargas, y el asistente es otro
 * servicio que puede no estar desplegado. Si lanzara, el síntoma sería "no
 * puedo entrar a configuración" en vez de "el asistente no responde".
 * `guardar` sí lanza: ahí alguien apretó un botón y tiene que enterarse.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * Los ajustes de la Bandeja, o `null` si no hay asistente o no contesta.
 * @returns {Promise<{ sla_toma_minutos: number, umbral_rx_dbm: number | null } | null>}
 */
export async function leerAjustesBandeja(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/bandeja?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Guarda los dos ajustes.
 *
 * Manda los dos SIEMPRE, incluso el que no cambió: el motor reemplaza el par
 * completo, así que omitir uno lo borraría. Vacío se envía como el "sin
 * definir" que corresponde a cada uno --0 para el plazo, null para el
 * umbral-- y no como ausencia.
 *
 * El rango lo valida el motor (0-1440 minutos, -40..0 dBm) y su mensaje de
 * error es más útil que uno genérico, así que se deja pasar tal cual.
 *
 * @param {{ sla_toma_minutos: string | number, umbral_rx_dbm: string | number | null }} valores
 */
export async function guardarAjustesBandeja(locals, fetch, valores) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) {
    throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  }

  const crudo = valores.umbral_rx_dbm;
  const resp = await fetch(`${cfg.baseUrl}/configuracion/bandeja`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      tenant: cfg.tenant,
      sla_toma_minutos: valores.sla_toma_minutos === '' ? 0 : valores.sla_toma_minutos,
      umbral_rx_dbm: crudo === '' || crudo === undefined ? null : crudo
    })
  });

  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(datos.error || 'El asistente rechazó el cambio.');
  }
  return datos;
}
