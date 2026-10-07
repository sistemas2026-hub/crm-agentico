/**
 * Cuadrillas — quiénes son, y qué hacen cada día.
 *
 * Server-only, por el mismo `apiRequest` que el resto del módulo. No hay un
 * segundo cliente HTTP.
 *
 * DOS PREGUNTAS DISTINTAS, DOS FUNCIONES
 *   `leerCuadrillas`  quiénes son   — cambia casi nunca
 *   `leerJornadaDeCuadrillas`  qué hacen HOY — cambia cada mañana
 *
 * Mezclarlas haría que armar el día pareciera editar la cuadrilla, y es justo
 * lo contrario: la cuadrilla sigue siendo la misma, lo que cambia es su labor
 * y quién la integra.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * Las cuadrillas de la empresa.
 *
 * El error viaja declarado y no como lista vacía: una empresa sin cuadrillas
 * todavía y una lectura que falló se dibujan distinto.
 *
 * @param {{ cookies: any }} ctx
 * @param {boolean} todas  incluir las dadas de baja
 */
export async function leerCuadrillas(ctx, todas = false) {
  try {
    const d = await apiRequest(
      `/campo/cuadrillas/${todas ? '?todas=1' : ''}`, {}, ctx
    );
    return { cuadrillas: d?.cuadrillas ?? [], error: false };
  } catch {
    return { cuadrillas: [], error: true };
  }
}

/** @param {{ cookies: any }} ctx @param {Record<string, any>} cuerpo */
export async function crearCuadrilla(ctx, cuerpo) {
  return apiRequest('/campo/cuadrillas/', { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id @param {Record<string, any>} cuerpo */
export async function editarCuadrilla(ctx, id, cuerpo) {
  return apiRequest(`/campo/cuadrillas/${id}/`, { method: 'PATCH', body: cuerpo }, ctx);
}

/**
 * Lo que cada cuadrilla hace ESE día.
 *
 * Exige la fecha: «la jornada» sin día no significa nada, igual que en
 * programación. Por eso la pantalla abre con una fecha y nunca con «todo».
 *
 * @param {{ cookies: any }} ctx
 * @param {string} dia  YYYY-MM-DD
 */
export async function leerJornadaDeCuadrillas(ctx, dia) {
  try {
    const d = await apiRequest(
      `/campo/cuadrillas/jornada/?fecha=${encodeURIComponent(dia)}`, {}, ctx
    );
    return { jornadas: d?.jornadas ?? [], error: false };
  } catch {
    return { jornadas: [], error: true };
  }
}

/**
 * Arma (o reescribe) el día de una cuadrilla.
 *
 * Es idempotente por cuadrilla y fecha: mandarlo dos veces deja lo mismo que
 * mandarlo una. Armar el día se corrige varias veces antes de que empiece.
 *
 * @param {{ cookies: any }} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function armarJornada(ctx, cuerpo) {
  return apiRequest(
    '/campo/cuadrillas/jornada/', { method: 'POST', body: cuerpo }, ctx
  );
}
