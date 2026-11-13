/**
 * QUE FILTRO ESTA RECORTANDO LA COLA  --  06/11/2026
 *
 * El usuario mando dos capturas, antes y despues de escribir "mario" en el
 * buscador: «el antes y despues de la busqueda se desaparecen los ticket».
 * Lo que pasaba:
 *
 *     sin buscar   Todas 721 · Cartera 522 · Soporte 57 · Ventas 87 · Operativo 50
 *     buscando     Todas  10 · Cartera   4 · Soporte  6 · Ventas  0 · Operativo  0
 *
 * Los numeros no estaban mal -- pulsar Ventas con esa busqueda puesta muestra
 * exactamente 0 --, pero la pantalla no decia que estaba filtrando, asi que
 * un area con 87 tickets vivos se leia como un area vacia. La unica pista era
 * una linea de 11px, "Estos numeros describen la cola filtrada", que ademas
 * salia con CUALQUIER parametro en la URL: '?area=soporte' sin buscar nada ya
 * la disparaba, porque miraba 'url.search' -- la query string entera -- en vez
 * de los parametros que de verdad recortan.
 *
 * Aca se decide ESO, en codigo y probado: cuales de los parametros de la URL
 * recortan lo que cuentan las tarjetas.
 */

/**
 * Los parametros que viajan a las DOS consultas (la principal y la de los
 * totales) y por lo tanto recortan lo que dicen las tarjetas.
 *
 * 'area', 'vista', 'incluir_mios' y 'offset' NO estan a proposito: el cargador
 * los borra de 'paramsGlobal' antes de pedir los totales, asi que las tarjetas
 * ya los ignoran. 'orden', 'limit' y 'all' tampoco recortan: cambian el orden,
 * el tamano de la pagina y que estados entran, no cuantos hay de cada area.
 *
 * Los cinco del medio son FILTER_FIELDS de lib/server/v2/tickets.js. Si uno
 * se agrega alla y no aca, su aviso no sale: la prueba de este modulo compara
 * las dos listas para que no se separen en silencio.
 */
export const FILTROS_QUE_RECORTAN = [
  'search',
  'assigned_to',
  'priority',
  'case_type',
  'sla_breached',
  'tags'
];

/** Como se nombra cada filtro en el aviso. */
const NOMBRES = {
  assigned_to: 'responsable',
  priority: 'prioridad',
  case_type: 'tipo',
  sla_breached: 'SLA vencido',
  tags: 'etiqueta'
};

/**
 * Lee de la URL que esta recortando la cola.
 *
 * Un parametro presente pero VACIO ('?search=') no cuenta: es lo que deja un
 * formulario enviado sin escribir nada, y avisar ahi de un filtro que no
 * existe entrena a ignorar el aviso.
 *
 * @param {URL | { searchParams?: URLSearchParams } | null | undefined} url
 * @returns {{ busqueda: string, otros: string[], hay: boolean }}
 *   busqueda: el texto buscado, '' si no hay.
 *   otros:    los demas filtros activos, por su nombre visible, sin repetir.
 *   hay:      si algo esta recortando. Es lo que decide si el aviso sale.
 */
export function filtrosDeLaCola(url) {
  const p = url?.searchParams;
  if (!p) return { busqueda: '', otros: [], hay: false };

  const busqueda = (p.get('search') ?? '').trim();
  const otros = [];
  for (const clave of FILTROS_QUE_RECORTAN) {
    if (clave === 'search') continue;
    //  getAll: un filtro repetible ('?tags=a&tags=b') se nombra una vez.
    const alguno = p.getAll(clave).some((v) => v.trim() !== '');
    if (alguno) otros.push(NOMBRES[clave] ?? clave);
  }
  return { busqueda, otros, hay: Boolean(busqueda) || otros.length > 0 };
}

/**
 * El mismo enlace sin lo que recorta: lo que destraba al que se perdio.
 *
 * Tambien borra 'offset': quitar el filtro agranda la cola, y quedarse en la
 * pagina 4 de la cola vieja lleva a un lugar que no es el que se pidio.
 * 'area', 'vista' y 'orden' se CONSERVAN -- son la pantalla donde esta parado,
 * no el filtro del que quiere salir.
 *
 * @param {URL} url
 * @returns {string} ruta + query, lista para un href
 */
export function sinLosFiltros(url) {
  const p = new URLSearchParams(url.searchParams);
  for (const clave of FILTROS_QUE_RECORTAN) p.delete(clave);
  p.delete('offset');
  const query = p.toString();
  return query ? `${url.pathname}?${query}` : url.pathname;
}
