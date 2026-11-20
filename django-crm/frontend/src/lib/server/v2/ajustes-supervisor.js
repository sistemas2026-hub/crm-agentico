/**
 * Ajustes del Supervisor — delegar o quitar cada tarea con un clic (27/10/2026).
 *
 * Server-only, por el mismo `apiRequest` que el resto del CRM. La regla vive en
 * el backend (`operaciones/ajustes_views.py`, que escribe por `td.delegar` y
 * `td.quitar`, las mismas que el chat): acá no se valida nada que allá no se
 * valide.
 */
import { apiRequest } from '$lib/api-helpers.js';

const RUTA = '/operaciones/supervisor/ajustes/';

/** @param {{ cookies: any }} ctx */
export async function leerAjustes(ctx) {
  return apiRequest(RUTA, {}, ctx);
}

/**
 * @param {{ cookies: any }} ctx
 * @param {{ clave: string, delegar: boolean, motivo: string }} cambio
 */
export async function cambiarTarea(ctx, cambio) {
  return apiRequest(RUTA, { method: 'POST', body: cambio }, ctx);
}
