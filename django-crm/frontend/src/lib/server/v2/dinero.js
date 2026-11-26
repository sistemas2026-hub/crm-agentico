/**
 * EL DINERO QUE RECIBE EL TÉCNICO (26/11/2026). Ver campo/dinero.py.
 *
 * El técnico cobra en la casa (instalación, equipos o material extra) y lo
 * anota en un campo de la plantilla marcado como dinero. La oficina ve aquí
 * cuánto tiene cada técnico por entregar y lo recibe.
 *
 * Leer NUNCA inventa un cero: si la API falla, `error` lo dice. «Nadie debe
 * nada» porque no se pudo leer es lo peor que esta pantalla podría mostrar.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/** @param {any} cookies */
export async function leerDinero(cookies) {
  try {
    const d = await apiRequest('/campo/dinero/', {}, cookies);
    return {
      configurado: Boolean(d?.configurado),
      tecnicos: d?.tecnicos ?? [],
      ultimas: d?.ultimas ?? [],
      error: '',
      sinPermiso: false
    };
  } catch (err) {
    const e = /** @type {any} */ (err);
    return {
      configurado: true,
      tecnicos: [],
      ultimas: [],
      error: mensajeDeError(e, 'No se pudo leer el dinero de los técnicos.'),
      sinPermiso: e?.status === 403
    };
  }
}

/**
 * La oficina recibe del técnico el dinero de esas órdenes, con la cifra que
 * mostraba la pantalla: si cambió, el servidor contesta 409 y no recibe nada.
 * @param {any} cookies
 * @param {string} tecnicoId
 * @param {{ orden_id: string, monto: number }[]} ordenes
 */
export async function recibirDinero(cookies, tecnicoId, ordenes) {
  return apiRequest(
    '/campo/dinero/recibir/',
    { method: 'POST', body: { tecnico_id: tecnicoId, ordenes } },
    cookies
  );
}
