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

/**
 * `grupo`, `categoria_nombre` y `exige_nota` los agrega el motor desde el
 * 10/11/2026 (nucleo/relevo/desenlaces.py::catalogo). Opcionales a proposito:
 * un motor anterior no los manda, y la pantalla tiene que seguir cerrando.
 *
 * @typedef {{codigo: string, nombre: string, categoria_base: string, origen: string,
 *   grupo?: string, categoria_nombre?: string, exige_nota?: boolean}} Desenlace
 */

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
  const elegido = catalogo.find((d) => d.codigo === codigo);
  if (!elegido) return 'Ese código ya no está en el catálogo.';
  if (nota.length > MAX_NOTA) return `La nota no puede pasar de ${MAX_NOTA} caracteres.`;
  // «Otro» sin una línea que lo explique no cuenta nada (10/11/2026). El
  // motor lo rechaza igual; esto es para decirlo antes de apretar.
  if (elegido.exige_nota && !nota.trim()) return `Con «${elegido.nombre}», contá qué pasó en la nota.`;
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
 * Con su NOMBRE cuando el motor lo manda: "red_distribucion" al lado de
 * "Poste 17" es un identificador, no algo que se lee.
 *
 * @param {Desenlace} d
 */
export function categoriaVisible(d) {
  if (d.origen !== 'tenant' || d.categoria_base === d.codigo) return '';
  return d.categoria_nombre || d.categoria_base;
}

/** Los dos grupos del panel, en orden. La clave es la que manda el motor. */
export const GRUPOS = /** @type {const} */ ([
  { clave: 'falla', titulo: 'Dónde estuvo la falla' },
  { clave: 'otra_cosa', titulo: 'No era una falla de la red' }
]);

/**
 * El catalogo partido en las dos preguntas que contesta (10/11/2026): dónde
 * fallo, o qué necesitaba el cliente si no era una falla. En una sola grilla
 * de doce se leian mezcladas, y el orden del motor --de la casa del cliente
 * hacia la red-- se perdia porque la grilla lo recorria de costado.
 *
 * Respeta el orden del motor dentro de cada grupo y no deja ninguno vacio.
 * Si el motor no manda `grupo` (uno anterior a este cambio), devuelve UN
 * grupo sin titulo con todo: inventar a que grupo va cada codigo seria tener
 * una segunda copia de la regla, y la regla vive en el motor.
 *
 * @param {Desenlace[]} catalogo
 * @returns {{clave: string, titulo: string, desenlaces: Desenlace[]}[]}
 */
export function agruparDesenlaces(catalogo) {
  if (!catalogo.some((d) => d.grupo)) {
    return catalogo.length ? [{ clave: 'todos', titulo: '', desenlaces: catalogo }] : [];
  }
  const conocidos = new Set(GRUPOS.map((g) => g.clave));
  return GRUPOS.map((g) => ({
    ...g,
    // Un grupo que este motor todavia no conoce no se pierde: va al segundo,
    // que es el de "no era una falla de la red".
    desenlaces: catalogo.filter((d) =>
      g.clave === 'otra_cosa' ? !conocidos.has(d.grupo ?? '') || d.grupo === g.clave : d.grupo === g.clave
    )
  })).filter((g) => g.desenlaces.length);
}
