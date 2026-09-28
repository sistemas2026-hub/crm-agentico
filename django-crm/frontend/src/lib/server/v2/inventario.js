import { apiRequest } from '$lib/api-helpers.js';

/**
 * El inventario: existencias, despacho y la historia de un aparato.
 *
 * POR QUÉ VIVE BAJO `$lib/server`
 * SvelteKit se niega a empaquetar ese directorio en el código del cliente, y el
 * token de acceso es una cookie httpOnly. La empresa nunca es un parámetro: es
 * un claim dentro del JWT y el backend lo lee de ahí.
 *
 * LOS ENDPOINTS NO LLEVAN `/api`
 * `API_BASE_URL` de api-helpers.js ya lo trae, asi que un endpoint que lo
 * repita termina en `/api/api/campo/...` y el backend devuelve 404. Se vio el
 * 28/09/2026: la pantalla salio entera con el aviso de «no se pudo leer», que
 * es lo que tenia que hacer, y el 404 estaba en el log del frontend.
 *
 * QUE RECIBEN, Y POR QUE NO ES `locals`
 * `apiRequest` saca el token de `ctx.cookies` (o de `ctx` si ya es el objeto
 * de cookies). En un `load` de SvelteKit `locals` NO tiene `.cookies`, asi que
 * pasarselo devuelve un token vacio y toda lectura falla en silencio -- se vio
 * el 28/09/2026: la pantalla salio entera y sin un dato. Se pasa `{ cookies }`,
 * igual que `listTickets` y los demas modulos v2.
 *
 * NINGUNA DE ESTAS FUNCIONES DEVUELVE UN CERO INVENTADO
 * Si el CRM no responde, devuelven la forma vacía Y `error: true`. La distinción
 * importa y es la lección de la franja del Centro de Mando: un «0 agentes» falso
 * hace creer que todo está bien, mientras un «no disponible» obliga a mirar. Una
 * bodega que dice 0 conectores porque la API falló es exactamente el mismo
 * defecto, y en inventario cuesta un viaje en vano de un técnico.
 */

/**
 * Todas las ubicaciones con sus existencias, para la vista general.
 *
 * @param {{cookies: any}} ctx
 * @returns {Promise<{ ubicaciones: any[], error: boolean }>}
 */
export async function leerExistencias(ctx) {
  try {
    const datos = await apiRequest('/campo/inventario/existencias/', {}, ctx);
    return { ubicaciones: datos?.ubicaciones ?? [], error: false };
  } catch {
    return { ubicaciones: [], error: true };
  }
}

/**
 * El catálogo de materiales. Lo necesita el formulario de despacho para saber
 * qué material exige número de serie.
 *
 * @param {{cookies: any}} ctx
 * @returns {Promise<{ materiales: any[], error: boolean }>}
 */
export async function leerCatalogo(ctx) {
  try {
    const datos = await apiRequest('/campo/inventario/catalogo/', {}, ctx);
    return { materiales: datos?.materiales ?? [], error: false };
  } catch {
    return { materiales: [], error: true };
  }
}

/**
 * Las ubicaciones, sin existencias. Para los selectores.
 *
 * @param {{cookies: any}} ctx
 * @returns {Promise<{ ubicaciones: any[], error: boolean }>}
 */
export async function leerUbicaciones(ctx) {
  try {
    const datos = await apiRequest('/campo/inventario/ubicaciones/', {}, ctx);
    return { ubicaciones: datos?.ubicaciones ?? [], error: false };
  } catch {
    return { ubicaciones: [], error: true };
  }
}

/**
 * La historia de un aparato por su serie.
 *
 * @param {{cookies: any}} ctx
 * @param {string} serie
 * @returns {Promise<{ activos: any[], error: boolean, noExiste: boolean }>}
 */
export async function leerSerie(ctx, serie) {
  try {
    const datos = await apiRequest(
      `/campo/inventario/serie/${encodeURIComponent(serie)}/`, {}, ctx
    );
    return { activos: datos?.activos ?? [], error: false, noExiste: false };
  } catch (e) {
    // 404 no es un fallo: es la respuesta a «no hay ningún aparato con esa
    // serie». Mezclarlo con un error de red haría que la pantalla dijera
    // «no se pudo consultar» cuando la verdad es «no existe».
    const noExiste = /404/.test(String(e?.message ?? e));
    return { activos: [], error: !noExiste, noExiste };
  }
}

/**
 * Registrar material que entra.
 *
 * @param {{cookies: any}} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function registrarEntrada(ctx, cuerpo) {
  return apiRequest('/campo/inventario/entradas/',
    { method: 'POST', body: cuerpo }, ctx);
}

/**
 * Despachar un kit a un técnico.
 *
 * @param {{cookies: any}} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function despachar(ctx, cuerpo) {
  return apiRequest('/campo/inventario/despachos/',
    { method: 'POST', body: cuerpo }, ctx);
}

/**
 * Recibir una devolución.
 *
 * @param {{cookies: any}} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function recibirDevolucion(ctx, cuerpo) {
  return apiRequest('/campo/inventario/devoluciones/',
    { method: 'POST', body: cuerpo }, ctx);
}

/**
 * A quién se le puede despachar.
 *
 * Va por la ruta de campo y no por `/users/get-teams-and-users/`, que devuelve
 * 403 «Organization context is required» con el mismo JWT que estas rutas
 * aceptan. Sin esto el selector de personas quedaba vacío y no se podía
 * despachar desde la pantalla, por un endpoint ajeno.
 *
 * @param {{cookies: any}} ctx
 * @returns {Promise<{ personas: any[], error: boolean }>}
 */
export async function leerPersonas(ctx) {
  try {
    const datos = await apiRequest('/campo/inventario/personas/', {}, ctx);
    return { personas: datos?.personas ?? [], error: false };
  } catch {
    return { personas: [], error: true };
  }
}
