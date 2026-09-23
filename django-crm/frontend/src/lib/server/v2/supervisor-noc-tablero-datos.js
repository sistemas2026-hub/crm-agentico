/**
 * Los dos bloques del tablero que hasta hoy no tenían backend: el feed de
 * actividad y el mapa de operación.
 *
 * Server-only. Vive aparte de `supervisor-noc.js` --que resuelve las ACCIONES
 * del Supervisor-- porque esto solo lee. Y aparte de `$lib/v2/supervisor-noc-
 * tablero.js`, que corre en el navegador y solo da forma a lo que ya llegó.
 *
 * NINGUNO DE LOS DOS CONVIERTE UN VACÍO EN UN ERROR
 * -------------------------------------------------
 * Una organización sin actividad y un mapa sin coordenadas contestan 200 con
 * la lista vacía y su motivo. Tratar eso como fallo haría que la pantalla
 * gritara «no se pudo leer» cuando lo cierto es «todavía no hay nada», que es
 * justo la distinción que este tablero existe para mostrar.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { traducirError } from './supervisor-noc.js';

/**
 * Los últimos eventos del Supervisor y de quienes revisaron sus propuestas.
 *
 * Sale de `common.Activity`, la bitácora que ya escribe `auditoria.registrar`:
 * no hay un registro nuevo ni un evento duplicado. El backend marca `es_ia`
 * cuando el autor fue el Supervisor y no una persona.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {number} limite
 */
export async function leerActividad({ cookies }, limite = 20) {
  try {
    const d = await apiRequest(
      `/operaciones/actividad-supervisor/?limite=${limite}`,
      {},
      { cookies }
    );
    return { count: d?.count ?? 0, eventos: d?.resultados ?? [], error: null };
  } catch (/** @type {any} */ err) {
    return { count: null, eventos: [], error: traducirError(err, 'la actividad del Supervisor') };
  }
}

/**
 * Los puntos del mapa, y el motivo cuando no hay ninguno.
 *
 * Las coordenadas salen de `OrdenTrabajo.gps_lat/gps_lng`. Del cliente no
 * viaja nada: el punto lleva el número de orden, su estado y su posición.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 */
export async function leerUbicaciones({ cookies }) {
  try {
    const d = await apiRequest('/operaciones/ubicaciones/', {}, { cookies });
    return {
      puntos: d?.puntos ?? [],
      disponible: d?.disponible ?? false,
      motivo: d?.motivo ?? '',
      sinPosicion: d?.ordenes_sin_posicion ?? 0,
      leyenda: d?.leyenda ?? null,
      error: null
    };
  } catch (/** @type {any} */ err) {
    return {
      puntos: [],
      disponible: false,
      motivo: '',
      sinPosicion: 0,
      leyenda: null,
      error: traducirError(err, 'el mapa de operación')
    };
  }
}
