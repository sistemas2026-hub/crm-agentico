/**
 * LA INSTALACIÓN QUE VALIDA UNA PERSONA (26/11/2026). Ver campo/instalacion.py.
 *
 * El técnico finaliza; la instalación se crea en el proveedor; una persona la
 * revisa aquí y la aprueba —eso la ACTIVA en el proveedor— o la devuelve. Al
 * técnico le llega que valide el servicio y la entregue, y al confirmar la
 * entrega se cierra el ticket.
 *
 * Leer NUNCA inventa una lista vacía: si la API falla, `error` lo dice.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/** @param {any} cookies */
export async function leerPorActivar(cookies) {
  try {
    const d = await apiRequest('/campo/instalaciones/por-activar/', {}, cookies);
    //  LAS TRABADAS (27/11/2026): contratos cuya instalación no quedó creada
    //  en el proveedor, o no se sabe. Con o sin solicitud.
    return { instalaciones: d?.instalaciones ?? [], trabadas: d?.trabadas ?? [], error: '' };
  } catch (err) {
    return { instalaciones: [], trabadas: [], error: mensajeDeError(err, 'No se pudieron leer las instalaciones por activar.') };
  }
}

/**
 * La persona aprueba: el servidor pide la activación en el proveedor (corre
 * después, en una tarea). 409 con el porqué si no se puede.
 * @param {any} cookies
 * @param {string} ordenId
 */
export async function aprobarInstalacion(cookies, ordenId) {
  return apiRequest(`/campo/trabajos/${encodeURIComponent(ordenId)}/aprobar-instalacion/`,
    { method: 'POST', body: {} }, cookies);
}

/**
 * EL CLIENTE FIRMA EL CONTRATO DEL PROVEEDOR (26/11/2026): pedir otra vez que
 * se prepare, cuando falló o quedó «por revisar» y alguien ya miró en el
 * proveedor. 202: se encoló; 409 con el porqué si no se puede.
 * @param {any} cookies
 * @param {string} contratoId
 */
export async function subirFotosDelTrabajo(cookies, contratoId) {
  return apiRequest(`/campo/contratos/${encodeURIComponent(contratoId)}/subir-fotos/`,
    { method: 'POST', body: {} }, cookies);
}

/**
 * Pedir otra vez que se prepare el contrato del proveedor.
 * @param {any} cookies
 * @param {string} contratoId
 */
export async function prepararContratoProveedor(cookies, contratoId) {
  return apiRequest(`/campo/contratos/${encodeURIComponent(contratoId)}/preparar-contrato-proveedor/`,
    { method: 'POST', body: {} }, cookies);
}
