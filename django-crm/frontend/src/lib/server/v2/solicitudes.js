/**
 * Solicitudes de instalación: la bandeja donde se decide, y sus ajustes.
 *
 * Todo va contra Django y no contra el motor, aunque los ajustes terminen en
 * la config del tenant: la bandeja vive en Django (es una tabla nuestra), y
 * partir la pantalla entre dos backends por un par de variables sólo agrega
 * un lugar más donde algo puede fallar. Django hace ese salto por dentro.
 *
 * SE AUTENTICA CON 'apiRequest', COMO LOS OTROS 54 MÓDULOS
 * -------------------------------------------------------
 * Este archivo tenía su propio `pedir()` con un fetch pelado que mandaba sólo
 * 'Content-Type'. Sin el JWT no viaja nada: y la organización es un claim
 * DENTRO de ese token, no una cabecera aparte. El backend exige
 * `HasOrgContext` y respondía "Organization context is required. Please login
 * again." en toda la pantalla.
 *
 * El síntoma engañaba: la bandeja mostraba "No hay solicitudes esperando" —su
 * estado vacío— con el error arriba, así que parecía que la solicitud enviada
 * se había perdido. Estaba guardada; nunca se pudo leer. Encontrado el
 * 08/09/2026 llenando el formulario de punta a punta.
 *
 * Las funciones reciben ahora 'cookies' (o 'locals') en vez de 'fetch', que es
 * de donde apiRequest saca el token.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * Las solicitudes que esperan una decisión. Nunca lanza: no poder listar es
 * una pantalla vacía con un aviso, no un error que tumba la navegación.
 * @param {any} cookies
 * @param {string} estado
 */
export async function leerBandeja(cookies, estado = '') {
  try {
    const q = estado ? `?estado=${encodeURIComponent(estado)}` : '';
    const datos = await apiRequest(`/solicitudes/bandeja/${q}`, {}, cookies);
    return { solicitudes: datos?.solicitudes ?? [] };
  } catch (/** @type {any} */ err) {
    return { solicitudes: [], error: err?.message || 'No se pudo leer la bandeja.' };
  }
}

/**
 * Los dos equipos configurados hoy.
 * @param {any} cookies
 */
export async function leerAjustes(cookies) {
  try {
    return await apiRequest('/solicitudes/ajustes/', {}, cookies);
  } catch (/** @type {any} */ err) {
    return { error: err?.message || 'No se pudo leer la configuración.' };
  }
}

/**
 * El personal de WispHub, para elegir de una lista en vez de escribir un id.
 * @param {any} cookies
 */
export async function leerTecnicos(cookies) {
  try {
    const datos = await apiRequest('/solicitudes/tecnicos/', {}, cookies);
    return datos?.tecnicos ?? [];
  } catch {
    // Sin lista, la pantalla cae a campos de texto: poder configurar aunque
    // WispHub no responda vale más que una lista perfecta.
    return [];
  }
}

/**
 * @param {any} cookies
 * @param {Record<string, unknown>} valores
 */
export async function guardarAjustes(cookies, valores) {
  // El cuerpo va como OBJETO, no como texto: apiRequest hace el JSON.stringify
  // por dentro, y pasarlo ya serializado lo mandaría con comillas de más.
  return apiRequest('/solicitudes/ajustes/', { method: 'PUT', body: valores }, cookies);
}

/**
 * Aprobar o rechazar. Aprobar mueve el ticket de WispHub al equipo que instala.
 * @param {any} cookies
 * @param {string} id
 * @param {boolean} aprueba
 * @param {string} nota
 */
export async function decidir(cookies, id, aprueba, nota) {
  return apiRequest(
    `/solicitudes/${id}/decidir/`,
    { method: 'POST', body: { aprueba, nota } },
    cookies
  );
}
