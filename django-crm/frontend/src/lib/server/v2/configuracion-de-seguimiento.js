import { apiRequest } from '$lib/api-helpers.js';

/**
 * Lo que el Supervisor hace solo con el seguimiento, por empresa (30/10/2026):
 * recordarle al técnico la orden sin reporte. Ver
 * campo/configuracion_de_seguimiento_views.py.
 *
 * Que CIERRE solo no se enciende acá: es una tarea que se le delega desde su
 * chat, con el nivel 3 y el interruptor de emergencia, como las otras.
 */

/** @param {{ cookies: any }} ctx */
export async function leerConfiguracionDeSeguimiento(ctx) {
  try {
    return { configuracion: await apiRequest('/campo/seguimiento/configuracion/', {}, ctx), error: false };
  } catch {
    return { configuracion: null, error: true };
  }
}

/**
 * Del formulario: una casilla marcada llega como 'on'; desmarcada, no llega.
 *
 * @param {FormData} f
 */
export function cuerpoDeSeguimiento(f) {
  return { recordar_al_tecnico: f.get('recordar_al_tecnico') === 'on' };
}

/**
 * @param {{ cookies: any }} ctx
 * @param {{ recordar_al_tecnico: boolean }} cuerpo
 */
export async function guardarConfiguracionDeSeguimiento(ctx, cuerpo) {
  return apiRequest('/campo/seguimiento/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
