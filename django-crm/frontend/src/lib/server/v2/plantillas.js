/**
 * Plantillas de trabajo — qué anota y qué fotos saca el técnico en cada visita.
 *
 * Server-only, por el mismo `apiRequest` que el resto del módulo. Lo que una
 * plantilla PUEDE contener, y por qué esa lista es cerrada, lo decide el
 * backend (`campo/plantillas.py`): acá no se valida nada que allá no se
 * valide, para que no haya dos versiones de la regla.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * El texto para quien edita.
 *
 * `apiRequest` pone en `message` el `error` (el CÓDIGO, «FALTAN_OPCIONES») y
 * deja la respuesta entera en `body`. La frase que sirve está en
 * `body.detalle`; leer `message` mostraría el código.
 *
 * @param {any} e
 * @param {string} porDefecto
 */
export function mensajeDePlantilla(e, porDefecto) {
  const b = e?.body ?? {};
  const motivos = Array.isArray(b.por_que_no) && b.por_que_no.length
    ? ` (${b.por_que_no.join('; ')})`
    : '';
  const texto = typeof b.detalle === 'string' && b.detalle.trim()
    ? b.detalle.trim()
    : typeof b.detail === 'string' && b.detail.trim()
      ? b.detail.trim()
      : porDefecto;
  return texto + motivos;
}

/** @param {{ cookies: any }} ctx */
export async function leerPlantillas(ctx) {
  try {
    const d = await apiRequest('/campo/plantillas/', {}, ctx);
    return {
      propias: d?.propias ?? [],
      catalogo: d?.catalogo ?? [],
      tipos: d?.tipos ?? [],
      labores: d?.labores ?? [],
      error: false
    };
  } catch {
    return { propias: [], catalogo: [], tipos: [], labores: [], error: true };
  }
}

/** @param {{ cookies: any }} ctx @param {string} id */
export async function leerPlantilla(ctx, id) {
  return apiRequest(`/campo/plantillas/${id}/`, {}, ctx);
}

/**
 * @param {{ cookies: any }} ctx
 * @param {{ base?: string, nombre?: string, labor?: string, definicion?: any }} cuerpo
 */
export async function crearPlantilla(ctx, cuerpo) {
  return apiRequest('/campo/plantillas/', { method: 'POST', body: cuerpo }, ctx);
}

/**
 * @param {{ cookies: any }} ctx @param {string} id
 * @param {{ definicion: any, nombre?: string, labor?: string }} cuerpo
 */
export async function publicarPlantilla(ctx, id, cuerpo) {
  return apiRequest(`/campo/plantillas/${id}/publicar/`,
    { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id @param {boolean} activo */
export async function activarPlantilla(ctx, id, activo) {
  return apiRequest(`/campo/plantillas/${id}/`,
    { method: 'PATCH', body: { activo } }, ctx);
}
