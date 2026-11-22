/**
 * «Fallas de red» — las caídas de PON vivas y el aviso a sus clientes
 * (30/10/2026, PRD §8.17, Ola 2).
 *
 * Server-only, por el mismo `apiRequest` que el resto del CRM. La regla vive en
 * el backend (`operaciones/aviso_de_caida.py`) y la lista la arma el motor: acá
 * no se decide a quién se le avisa.
 */
import { apiRequest } from '$lib/api-helpers.js';

const RUTA = '/operaciones/fallas-de-red/';

/** @param {{ cookies: any }} ctx */
export async function leerFallas(ctx) {
  return apiRequest(RUTA, {}, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id */
export async function prepararAviso(ctx, id) {
  return apiRequest(`${RUTA}${id}/aviso/`, { method: 'POST', body: { accion: 'preparar' } }, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id */
export async function aprobarAviso(ctx, id) {
  return apiRequest(`${RUTA}${id}/aviso/`, { method: 'POST', body: { accion: 'aprobar' } }, ctx);
}

/**
 * Detiene el envío en curso (22/11/2026). La tanda que ya está en el motor
 * termina y se cuenta; no sale ninguna más, tampoco el «ya volvió».
 * @param {{ cookies: any }} ctx @param {string} id @param {string} motivo
 */
export async function detenerAviso(ctx, id, motivo) {
  return apiRequest(`${RUTA}${id}/aviso/`, { method: 'POST', body: { accion: 'detener', motivo } }, ctx);
}

/**
 * A quién le llega el aviso aprobado (22/11/2026): los servicios, el nombre
 * cuando el CRM tiene un caso de ese servicio, y si su tanda ya salió.
 * @param {{ cookies: any }} ctx @param {string} id
 */
export async function leerDestinatarios(ctx, id) {
  return apiRequest(`${RUTA}${id}/aviso/`, {}, ctx);
}
