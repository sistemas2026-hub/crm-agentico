/**
 * PAGINAR UNA COLA LARGA
 * ======================
 *
 * EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 07/10/2026
 * ----------------------------------------------------------------
 * La cola de tickets traia 25 filas y el pie decia "Mostrando 25 de 47". Ahi
 * terminaba: no habia enlace, ni boton, ni forma de llegar a los otros 22.
 * Para quien tiene que trabajar esa cola, 22 tickets simplemente no existian.
 *
 * POR QUE CON ENLACES Y NO CON UN BOTON DE "VER MAS"
 * ---------------------------------------------------
 * Un 'offset' en la URL hace que una pagina concreta se pueda compartir,
 * recargar y dejar en el historial del navegador. Un boton que acumula filas
 * en memoria pierde todo eso en la primera recarga, y no sobrevive a que
 * alguien abra un ticket y vuelva atras -- que es lo que se hace todo el dia
 * en una cola.
 *
 * LAS URLS SE ARMAN ACA Y NO EN LA PANTALLA
 * ------------------------------------------
 * Porque hay que conservar TODOS los demas parametros -- el area, los
 * filtros, la vista, 'all=1' -- y perder uno manda a la persona a otra cola
 * sin avisar. Es una funcion pura, asi que se puede probar; dentro de un
 * 'load' no se podria, y eso ya dejo pasar un defecto en esta misma pantalla.
 */

/**
 * @param {URL} url        la peticion actual, con todos sus parametros
 * @param {number} total   cuantas filas hay en TODA la cola filtrada
 * @param {number} desde   el offset de la pagina que se esta mostrando
 * @param {number} porPagina
 * @returns {{desde:number, hasta:number, total:number, pagina:number,
 *            paginas:number, previa:string|null, siguiente:string|null}}
 */
export function calcularPaginacion(url, total, desde, porPagina) {
  const t = Math.max(Number(total) || 0, 0);
  const tam = Math.max(Number(porPagina) || 25, 1);
  //  Un offset mas alla del final no deja la pantalla en blanco: se trae a la
  //  ultima pagina real. Pasa al borrar tickets, o al seguir un enlace viejo.
  const tope = t === 0 ? 0 : Math.floor((t - 1) / tam) * tam;
  const d = Math.min(Math.max(Number(desde) || 0, 0), tope);

  const enlace = (offset) => {
    const u = new URL(url);
    //  Se conserva todo lo demas y solo se mueve el offset. 'limit' se deja
    //  como vino: si alguien pidio 100 por pagina, sigue en 100.
    if (offset > 0) u.searchParams.set('offset', String(offset));
    else u.searchParams.delete('offset');
    return u.pathname + (u.search || '');
  };

  return {
    desde: t === 0 ? 0 : d + 1,          // 1-indexado, para leerlo
    hasta: Math.min(d + tam, t),
    total: t,
    pagina: Math.floor(d / tam) + 1,
    paginas: Math.max(Math.ceil(t / tam), 1),
    previa: d > 0 ? enlace(Math.max(d - tam, 0)) : null,
    siguiente: d + tam < t ? enlace(d + tam) : null
  };
}
