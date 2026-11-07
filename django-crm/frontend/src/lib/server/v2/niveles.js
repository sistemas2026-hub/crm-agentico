/**
 * Niveles de respuesta — plazo y prioridad por asunto (24/10/2026).
 *
 * Server-only, por el mismo `apiRequest` que Plantillas. La regla vive en el
 * backend (`campo/niveles.py`): acá no se valida nada que allá no se valide.
 * Los errores llegan con la misma forma que los de Plantillas, así que se
 * leen con `mensajeDePlantilla`.
 */
import { apiRequest } from '$lib/api-helpers.js';

/** @param {{ cookies: any }} ctx */
export async function leerNiveles(ctx) {
  try {
    const d = await apiRequest('/campo/niveles-de-respuesta/', {}, ctx);
    return { niveles: d?.niveles ?? [], asuntos: d?.asuntos ?? [],
             ubica_el_supervisor: !!d?.ubica_el_supervisor, error: false };
  } catch {
    return { niveles: [], asuntos: [], ubica_el_supervisor: false, error: true };
  }
}

/**
 * @param {{ cookies: any }} ctx
 * @param {{ codigo: string, nombre?: string, plazo_dias?: number, prioridad?: string }[]} niveles
 */
export async function guardarNiveles(ctx, niveles) {
  return apiRequest('/campo/niveles-de-respuesta/',
    { method: 'PUT', body: { niveles } }, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} asunto @param {string} nivel */
export async function ponerNivelDeAsunto(ctx, asunto, nivel) {
  return apiRequest('/campo/niveles-de-respuesta/asunto/',
    { method: 'PUT', body: { asunto, nivel } }, ctx);
}
