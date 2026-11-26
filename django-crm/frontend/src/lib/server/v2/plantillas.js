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

/**
 * El material que se precarga en las órdenes de ese tipo de trabajo
 * (26/11/2026). Reemplaza la lista entera; no pide publicar una versión.
 *
 * @param {{ cookies: any }} ctx @param {string} id
 * @param {{ codigo: string, cantidad: number | string | null, campo?: string }[]} lineas
 */
export async function guardarMaterialHabitual(ctx, id, lineas) {
  return apiRequest(`/campo/plantillas/${id}/material-habitual/`,
    { method: 'PUT', body: { lineas } }, ctx);
}

/**
 * Las líneas del formulario: `material_codigo_<i>`, `material_cantidad_<i>` y
 * `material_campo_<i>` (el campo de la plantilla de donde sale la cantidad).
 * Una fila sin material se ignora (es la que se agregó y no se llenó); una
 * cantidad vacía viaja como `null` («la escribe el técnico»). Un número con
 * letras viaja como texto, para que el backend diga qué está mal.
 *
 * @param {FormData} f
 */
export function lineasDeMaterial(f) {
  /** @type {{ codigo: string, cantidad: number | string | null, campo: string }[]} */
  const lineas = [];
  const indices = [...f.keys()]
    .map((k) => /^material_codigo_(\d+)$/.exec(k)?.[1])
    .filter((i) => i !== undefined)
    .map(Number)
    .sort((a, b) => a - b);
  for (const i of indices) {
    const codigo = String(f.get(`material_codigo_${i}`) ?? '').trim();
    if (!codigo) continue;
    const crudo = String(f.get(`material_cantidad_${i}`) ?? '').trim().replace(',', '.');
    const n = Number(crudo);
    const campo = String(f.get(`material_campo_${i}`) ?? '').trim();
    lineas.push({ codigo, cantidad: crudo === '' ? null : Number.isFinite(n) ? n : crudo, campo });
  }
  return lineas;
}

/**
 * Los puntos de TV de ese tipo de trabajo (26/11/2026): el conector, cuántos
 * por punto y de entrada, el máximo, el cable y los spliters.
 *
 * @param {{ cookies: any }} ctx @param {string} id @param {Record<string, any>} datos
 */
export async function guardarPuntosDeTv(ctx, id, datos) {
  return apiRequest(`/campo/plantillas/${id}/puntos-de-tv/`,
    { method: 'PUT', body: datos }, ctx);
}

/**
 * El formulario de los puntos de TV, como lo espera el backend. La casilla
 * desmarcada viaja como `false` (el navegador no la manda). Los números viajan
 * como los escribió quien edita: el backend dice si están mal.
 *
 * @param {FormData} f
 */
export function puntosDeTvDel(f) {
  const texto = (/** @type {string} */ k) => String(f.get(k) ?? '').trim();
  const indices = [...f.keys()]
    .map((k) => /^tv_spliter_codigo_(\d+)$/.exec(k)?.[1])
    .filter((i) => i !== undefined)
    .map(Number)
    .sort((a, b) => a - b);
  return {
    activo: f.get('tv_activo') === 'on',
    conector: texto('tv_conector'),
    conectores_por_punto: texto('tv_por_punto'),
    conectores_de_entrada: texto('tv_entrada'),
    maximo_de_puntos: texto('tv_maximo'),
    cable: texto('tv_cable'),
    spliters: indices
      .map((i) => ({ codigo: texto(`tv_spliter_codigo_${i}`), salidas: texto(`tv_spliter_salidas_${i}`) }))
      .filter((s) => s.codigo)
  };
}

/** @param {{ cookies: any }} ctx @param {string} id @param {boolean} activo */
export async function activarPlantilla(ctx, id, activo) {
  return apiRequest(`/campo/plantillas/${id}/`,
    { method: 'PATCH', body: { activo } }, ctx);
}
