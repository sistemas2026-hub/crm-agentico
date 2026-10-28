/**
 * Canal de WhatsApp: estado del canal y las credenciales cifradas que lo
 * activan. El puente entre el CRM y el motor, mismo patron que
 * asistente-config.js.
 *
 * Server-only. Habla con crm-agentico (`PRIVATE_ASISTENTE_URL`), en la red
 * interna. El tenant sale del entorno del servidor y nunca del cliente.
 *
 * `leer*` no lanza -- mismo criterio que asistente-config.js: si el motor
 * esta caido, la pantalla de ajustes tiene que poder abrirse igual y decir
 * "no se pudo leer", no reventar. `guardar*`/`borrar*` SI lanzan: ahi alguien
 * apreto un boton y tiene que enterarse de que no se guardo.
 */
import { headersMotor } from './motor-headers.js';
import { destinoDelAsistente } from './tenant.js';

/**
 * Estado del canal: activo, version, numero visible, plantillas y los
 * NOMBRES de los cinco secretos que declara (nunca sus valores).
 * @returns {Promise<any | null>}
 */
export async function leerCanalWhatsapp(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/canales?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return null;
    const datos = await resp.json();
    return datos.whatsapp;
  } catch {
    return null;
  }
}

/**
 * Cómo ve Meta al número emisor (28/10/2026): calidad, estado, nombre visible,
 * modo. En vivo. null si el motor o Meta no contestan: la pantalla dice "no se
 * pudo leer" y sigue, como el resto de los `leer*`.
 *
 * @returns {Promise<{ numero_final: string | null, nombre_visible: string | null,
 *   estado_nombre: string | null, calidad: string | null, estado: string | null,
 *   modo: string | null, plataforma: string | null, nivel_envio: string | null,
 *   limite_diario: string | null, cuenta_oficial: boolean | null } | null>}
 */
export async function leerSaludWhatsapp(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return null;
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/canales/whatsapp/salud?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor(), signal: AbortSignal.timeout(10000) }
    );
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

/**
 * Que secretos de la empresa ya tienen un valor cargado -- nombre,
 * descripcion, pista (los ultimos 4 caracteres) y cuando se cargaron. Nunca
 * el valor.
 * @returns {Promise<any[]>}
 */
export async function listarSecretos(locals, fetch) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return [];
  try {
    const resp = await fetch(`${cfg.baseUrl}/secretos?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() });
    if (!resp.ok) return [];
    const datos = await resp.json();
    return datos.secretos ?? [];
  } catch {
    return [];
  }
}

/**
 * Prende/apaga el canal y fija el numero visible.
 * @param {{ activo: boolean, numero_visible?: string | null }} valores
 */
export async function guardarCanalWhatsapp(locals, fetch, valores) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/configuracion/canales/whatsapp`, {
    method: 'PUT',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ ...valores, tenant: cfg.tenant })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'El asistente rechazo el cambio.');
  return datos;
}

/**
 * Cifra y guarda un secreto. 'descripcion' es para que la lista diga para
 * que sirve sin tener que recordarlo.
 * @param {string} nombre
 * @param {string} valor
 * @param {string} [descripcion]
 */
export async function guardarSecreto(locals, fetch, nombre, valor, descripcion) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(`${cfg.baseUrl}/secretos`, {
    method: 'POST',
    headers: headersMotor({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tenant: cfg.tenant, nombre, valor, descripcion })
  });
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo guardar la credencial.');
}

/** @param {string} nombre */
export async function borrarSecreto(locals, fetch, nombre) {
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) throw new Error('Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const resp = await fetch(
    `${cfg.baseUrl}/secretos/${encodeURIComponent(nombre)}?tenant=${encodeURIComponent(cfg.tenant)}`,
    { method: 'DELETE', headers: headersMotor() }
  );
  const datos = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(datos.error || 'No se pudo borrar la credencial.');
}
