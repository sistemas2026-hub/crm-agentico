/**
 * El cierre con desenlace, del lado de la pantalla (B6).
 *
 * Aqui no hay nada de Svelte a proposito: esto se puede probar en node, sin
 * montar un componente, y por eso las reglas que importan viven aqui y no
 * dentro del marcado. Es el mismo patron que `acciones.js` y `legado.js`.
 *
 * LA REGLA QUE ESTE ARCHIVO SOSTIENE
 * ----------------------------------
 * No hay desenlace preseleccionado. Ni el primero de la lista, ni el ultimo
 * que uso el operador, ni 'otro'. Un valor por defecto hace que cerrar sea un
 * clic y que la columna se llene de lo que el formulario eligio, no de lo que
 * paso -- y esa columna existe justo para poder contar lo que paso.
 */

/** @typedef {{codigo: string, nombre: string, categoria_base: string, origen: string}} Desenlace */

/** Cuanto texto admite la nota. Lo mismo que el motor (§3.3). */
export const MAX_NOTA = 500;

/**
 * Trae el catalogo. Devuelve `[]` si falla, nunca lanza: una lista vacia
 * deshabilita el boton de cerrar con un motivo visible, que es mejor que una
 * pantalla rota sobre una conversacion que el operador esta leyendo.
 *
 * @param {typeof fetch} traer
 * @returns {Promise<{desenlaces: Desenlace[], error: string}>}
 */
export async function cargarDesenlaces(traer) {
  try {
    const resp = await traer('/api/conversaciones/desenlaces');
    const datos = await resp.json();
    if (!resp.ok) return { desenlaces: [], error: datos?.error || 'No se pudo leer el catálogo.' };
    return { desenlaces: datos?.desenlaces ?? [], error: '' };
  } catch (/** @type {any} */ err) {
    return { desenlaces: [], error: err?.message || 'No se pudo leer el catálogo.' };
  }
}

/**
 * Por que NO se puede cerrar todavia, o cadena vacia si se puede.
 *
 * Devuelve el motivo en vez de un booleano para que la pantalla pueda decirlo.
 * "Guardar" deshabilitado y sin explicacion es de las cosas que hacen que
 * alguien recargue la pagina tres veces antes de preguntar.
 *
 * @param {{codigo: string, nota?: string, catalogo: Desenlace[]}} entrada
 */
export function motivoParaNoCerrar({ codigo, nota = '', catalogo }) {
  if (!catalogo.length) return 'No hay códigos de cierre configurados.';
  if (!codigo) return 'Elegí en qué terminó el caso.';
  if (!catalogo.some((d) => d.codigo === codigo)) return 'Ese código ya no está en el catálogo.';
  if (nota.length > MAX_NOTA) return `La nota no puede pasar de ${MAX_NOTA} caracteres.`;
  return '';
}

/**
 * Lo que se manda al proxy. Sin nota vacia: `''` y "no puso nota" son la misma
 * cosa para quien lo lee despues, y mandar la cadena vacia haria que la
 * columna diga que hay una nota cuando no la hay.
 *
 * @param {{codigo: string, nota?: string}} entrada
 */
export function cuerpoDeCierre({ codigo, nota = '' }) {
  const limpia = nota.trim();
  return {
    desenlace: codigo,
    ...(limpia ? { nota: limpia } : {}),
    clave_operacion: crypto.randomUUID()
  };
}

/**
 * La categoria de plataforma a la que pertenece un codigo propio, para
 * mostrarla al lado del nombre. Vacia para los codigos base, que son su propia
 * categoria y repetirla solo haria ruido ("Facturación · facturacion").
 *
 * @param {Desenlace} d
 */
export function categoriaVisible(d) {
  return d.origen === 'tenant' && d.categoria_base !== d.codigo ? d.categoria_base : '';
}
