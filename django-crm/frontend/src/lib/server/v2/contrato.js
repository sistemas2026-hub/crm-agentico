import { apiRequest } from '$lib/api-helpers.js';

/**
 * Lo que cada empresa pone en el contrato que el técnico firma con el cliente
 * desde la app (13/11/2026). Ver campo/contrato_views.py.
 *
 * LOS SERVIDORES: el usuario, «zona es el servidor, así que debe mostrar los
 * dos y ahí se elige». Cada uno es el número de ZONA de WispHub (el de
 * /api/zonas/, no el de /api/router/: son catálogos con números distintos
 * aunque se llamen igual) y el nombre que verá el técnico.
 */

/** Cuántas filas de servidor ofrece el formulario. */
export const FILAS_DE_SERVIDOR = 6;

/** @param {{ cookies: any }} ctx */
export async function leerContrato(ctx) {
  try {
    return { configuracion: await apiRequest('/campo/contrato/configuracion/', {}, ctx), error: false };
  } catch {
    return { configuracion: null, error: true };
  }
}

/**
 * Del formulario al cuerpo del PUT.
 *
 * UNA FILA VACÍA SE IGNORA; UNA A MEDIAS NO. Si hay número sin nombre (o al
 * revés) se manda igual y el backend la rechaza con su mensaje: perderla en
 * silencio dejaría a la empresa creyendo que cargó un servidor que no está.
 *
 * El número llega como texto y el backend exige un entero; uno con letras se
 * manda tal cual para que el 400 diga qué está mal, en vez de convertirse en
 * NaN y desaparecer.
 *
 * @param {FormData} f
 */
export function cuerpoDeContrato(f) {
  /** @type {{ id_zona: number | string, nombre: string }[]} */
  const servidores = [];
  for (let i = 0; i < FILAS_DE_SERVIDOR; i++) {
    const id = String(f.get(`servidor_id_${i}`) ?? '').trim();
    const nombre = String(f.get(`servidor_nombre_${i}`) ?? '').trim();
    if (!id && !nombre) continue;
    servidores.push({ id_zona: /^\d+$/.test(id) ? Number(id) : id, nombre });
  }
  return {
    nit: String(f.get('nit') ?? '').trim(),
    servidores,
    texto_condiciones: String(f.get('texto_condiciones') ?? '')
  };
}

/** @param {{ cookies: any }} ctx @param {Record<string, any>} cuerpo */
export async function guardarContrato(ctx, cuerpo) {
  return apiRequest('/campo/contrato/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
