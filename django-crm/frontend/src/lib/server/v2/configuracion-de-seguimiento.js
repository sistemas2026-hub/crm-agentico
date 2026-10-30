import { apiRequest } from '$lib/api-helpers.js';

/**
 * Lo que el Supervisor hace solo con el seguimiento, por empresa (30/10/2026):
 * recordarle al técnico la orden sin reporte, y cerrar solo lo que su revisión
 * dio por bueno. Ver campo/configuracion_de_seguimiento_views.py.
 *
 * Encender el cierre solo NO abre ninguna compuerta del motor: el Supervisor
 * sigue pasando por la puerta autónoma, y sin Autonomía 2 no cierra nada.
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
  return {
    recordar_al_tecnico: f.get('recordar_al_tecnico') === 'on',
    supervisor_cierra_solo: f.get('supervisor_cierra_solo') === 'on'
  };
}

/**
 * @param {{ cookies: any }} ctx
 * @param {{ recordar_al_tecnico: boolean, supervisor_cierra_solo: boolean }} cuerpo
 */
export async function guardarConfiguracionDeSeguimiento(ctx, cuerpo) {
  return apiRequest('/campo/seguimiento/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
