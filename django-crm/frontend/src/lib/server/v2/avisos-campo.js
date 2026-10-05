/**
 * Los canales por donde esta empresa recibe los avisos de campo.
 *
 * POR QUE ESTA PANTALLA EXISTE
 * ----------------------------
 * La primera versión guardaba el webhook en una fila que **solo un programador
 * podía cargar**. La regla del proyecto no dice «configuración por empresa»:
 * dice *editable desde la interfaz y persistida por tenant, nunca un valor fijo
 * en código ni en un archivo que solo un desarrollador sabe editar*. Una fila
 * cargada por consola es la misma falla con otra cara — la empresa número dos
 * necesitaría una sesión de programación para pegar una URL.
 *
 * EL DESTINO NO VUELVE
 * --------------------
 * En un webhook esa URL **es** la credencial: cualquiera con ella publica en el
 * espacio. El backend devuelve una pista —los últimos caracteres— que alcanza
 * para distinguir un canal de otro. Mismo criterio que la pantalla de
 * credenciales del asistente, y por el mismo motivo.
 *
 * QUÉ TIPOS EXISTEN NO SE ESCRIBE ACÁ
 * -----------------------------------
 * La lista la devuelve el backend. El día que se agregue Mattermost aparece
 * sola, sin tocar el frontend — que es el punto de haber generalizado el modelo.
 */
import { apiRequest } from '$lib/api-helpers.js';

/** @param {{cookies: any}} ctx */
export async function leerAvisos(ctx) {
  try {
    const d = await apiRequest('/campo/avisos/canales/', {}, ctx);
    return {
      canales: d?.canales ?? [],
      urlBaseApp: d?.url_base_app ?? '',
      telefonoSoporte: d?.telefono_soporte ?? '',
      tipos: d?.tipos ?? [],
      puedeConfigurar: d?.puede_configurar === true,
      error: false
    };
  } catch (e) {
    // La pantalla se dibuja igual y lo dice. Dejarla en blanco haría que
    // parezca que la empresa no configuró nada cuando lo que pasó es que no se
    // pudo preguntar — son dos cosas distintas y se arreglan distinto.
    return { canales: [], urlBaseApp: '', tipos: [], puedeConfigurar: false, error: true };
  }
}

/** @param {{cookies: any}} ctx */
export async function crearCanal(ctx, cuerpo) {
  return apiRequest('/campo/avisos/canales/', { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{cookies: any}} ctx @param {string} id */
export async function cambiarCanal(ctx, id, cuerpo) {
  return apiRequest(`/campo/avisos/canales/${id}/`, { method: 'PATCH', body: cuerpo }, ctx);
}

/** @param {{cookies: any}} ctx @param {string} id */
export async function borrarCanal(ctx, id) {
  return apiRequest(`/campo/avisos/canales/${id}/`, { method: 'DELETE' }, ctx);
}

/**
 * Manda un mensaje de prueba por ese canal.
 *
 * Devuelve `{ llego, error }`. Un `llego: false` NO es un fallo de la página: es
 * el resultado de la prueba, y la pantalla lo muestra como tal.
 */
export async function probarCanal(ctx, id) {
  return apiRequest(`/campo/avisos/canales/${id}/probar/`, { method: 'POST', body: {} }, ctx);
}

/**
 * Lo que es de la EMPRESA y no de un canal: el dominio de los enlaces y el
 * teléfono al que llama el técnico desde la app.
 *
 * Van juntos en el mismo PUT porque son la misma fila. Mandarlos por separado
 * haría que guardar uno borre el otro.
 */
export async function guardarDominio(ctx, urlBaseApp, telefonoSoporte = '') {
  return apiRequest(
    '/campo/avisos/canales/',
    {
      method: 'PUT',
      body: { url_base_app: urlBaseApp, telefono_soporte: telefonoSoporte }
    },
    ctx
  );
}
