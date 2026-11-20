import { apiRequest } from '$lib/api-helpers.js';

/**
 * Qué dice la marca de agua de las fotos de campo, por empresa (12/11/2026).
 * Ver campo/marca_de_agua_views.py.
 *
 * EL LOGO NO SE CARGA ACÁ. Sale de `Org`, que ya tiene su pantalla en
 * /settings/organization. Esta pantalla lo usa y avisa si falta; dos lugares
 * para subir el mismo logo es un logo que diverge.
 */

/** @param {{ cookies: any }} ctx */
export async function leerMarcaDeAgua(ctx) {
  try {
    return { configuracion: await apiRequest('/campo/marca-de-agua/configuracion/', {}, ctx), error: false };
  } catch {
    return { configuracion: null, error: true };
  }
}

/** Las casillas del formulario. Desmarcada no llega, y su ausencia ES el apagado. */
const CASILLAS = [
  'activa',
  'mostrar_logo',
  'mostrar_empresa',
  'mostrar_tecnico',
  'mostrar_fecha',
  'mostrar_coordenadas',
  'estampar_capturas'
];

/**
 * Del formulario al cuerpo del PUT.
 *
 * LA OPACIDAD LLEGA COMO TEXTO Y EL BACKEND EXIGE UN ENTERO. Es la misma
 * lección que ya dejó escrita la configuración de seguimiento: un
 * `<input type="number">` pone '55' en el FormData, no 55, y el PUT valida
 * `isinstance(v, int)`. Mandar el texto da un 400 que dice «tiene que ser un
 * número» sobre un campo donde la persona escribió un número — el peor
 * mensaje posible.
 *
 * Un valor vacío o con letras NO se manda: el guardado queda como estaba en
 * vez de pisarse por un dedazo.
 *
 * @param {FormData} f
 */
export function cuerpoDeMarcaDeAgua(f) {
  /** @type {Record<string, any>} */
  const cuerpo = {};
  for (const c of CASILLAS) cuerpo[c] = f.get(c) === 'on';

  const posicion = String(f.get('posicion') ?? '').trim();
  if (posicion) cuerpo.posicion = posicion;

  const crudo = String(f.get('opacidad') ?? '').trim();
  if (/^\d+$/.test(crudo)) cuerpo.opacidad = Number(crudo);

  //  El texto extra SÍ se manda vacío: borrarlo es una acción legítima, y
  //  distinta de no tocarlo. La casilla de arriba no tiene ese problema
  //  porque su ausencia ya significa algo.
  cuerpo.texto_extra = String(f.get('texto_extra') ?? '').trim();

  return cuerpo;
}

/** @param {{ cookies: any }} ctx @param {Record<string, any>} cuerpo */
export async function guardarMarcaDeAgua(ctx, cuerpo) {
  return apiRequest('/campo/marca-de-agua/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
