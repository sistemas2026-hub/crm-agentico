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
 * Las series de un material que están HOY en una ubicación.
 *
 * Sale del índice `UbicacionDeActivo`, que guarda dónde está cada aparato, así
 * que es una consulta y no un recorrido del libro. El error viaja declarado:
 * una bodega sin ninguna de ese material devuelve lista vacía, y eso no es lo
 * mismo que no haber podido preguntar.
 *
 * @param {{cookies: any}} ctx
 * @param {string} ubicacion
 * @param {string} material  id o código
 * @returns {Promise<{ series: string[], error: boolean }>}
 */
export async function leerSeriesDisponibles(ctx, ubicacion, material) {
  try {
    const d = await apiRequest(
      `/campo/inventario/series/?ubicacion=${encodeURIComponent(ubicacion)}`
        + `&material=${encodeURIComponent(material)}`,
      {},
      ctx
    );
    return { series: d?.series ?? [], error: false };
  } catch {
    return { series: [], error: true };
  }
}

/**
 * Da de alta una bodega o un vehículo.
 *
 * NO sirve para la custodia de un técnico, y el backend lo rechaza: esa nace
 * sola la primera vez que se le despacha material, para que no pueda quedar
 * una custodia sin dueño ni dos para la misma persona.
 *
 * @param {{cookies: any}} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function crearUbicacion(ctx, cuerpo) {
  return apiRequest('/campo/inventario/ubicaciones/', { method: 'POST', body: cuerpo }, ctx);
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
    //
    // SE MIRA EL `status`, NO EL TEXTO. Esta línea buscaba "404" dentro del
    // mensaje, y el mensaje es el `detail` que manda Django --«No hay ningun
    // aparato con esa serie en esta empresa.»--, que no contiene ese número. Asi
    // que TODA serie inexistente se mostraba como «No se pudo consultar.
    // Reintentá», que es justo la confusión que este bloque existía para evitar.
    // Medido en la pantalla el 29/09/2026, y es el mismo defecto que
    // `lib/api-helpers.js` ya dejó documentado al agregar `failure.status`:
    // olfatear la prosa para recuperar un número que estaba ahí al lado.
    const noExiste = e?.status === 404;
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

/* ===========================================================================
 * FASE 2 -- reservas, traslados y conteo
 *
 * Las lecturas siguen la misma regla que las de arriba: forma vacía Y `error`
 * aparte, nunca un cero inventado. Y todas reciben `{ cookies }`, no `locals`.
 * =========================================================================== */

/**
 * Existencia, reservado y libre de una ubicación — las tres juntas.
 *
 * Juntas y no solo `libre`: «quedan 70» sin decir que hay 100 y 30 comprometidos
 * obliga a abrir otra pantalla para entender el número.
 *
 * @param {{cookies: any}} ctx
 * @param {string} ubicacion
 */
export async function leerLibre(ctx, ubicacion) {
  try {
    const d = await apiRequest(
      `/campo/inventario/libre/?ubicacion=${encodeURIComponent(ubicacion)}`, {}, ctx
    );
    return { materiales: d?.materiales ?? [], ubicacion: d?.ubicacion ?? null, error: false };
  } catch {
    return { materiales: [], ubicacion: null, error: true };
  }
}

/** @param {{cookies: any}} ctx @param {string} ubicacion @param {boolean} todas */
export async function leerReservas(ctx, ubicacion, todas = false) {
  try {
    const q = `?ubicacion=${encodeURIComponent(ubicacion)}${todas ? '&todas=1' : ''}`;
    const d = await apiRequest(`/campo/inventario/reservas/${q}`, {}, ctx);
    return { reservas: d?.reservas ?? [], error: false };
  } catch {
    return { reservas: [], error: true };
  }
}

/** @param {{cookies: any}} ctx @param {Record<string, any>} cuerpo */
export async function reservar(ctx, cuerpo) {
  return apiRequest('/campo/inventario/reservas/', { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{cookies: any}} ctx @param {string} id @param {string} motivo */
export async function liberarReserva(ctx, id, motivo) {
  return apiRequest(`/campo/inventario/reservas/${id}/liberar/`,
    { method: 'POST', body: { motivo } }, ctx);
}

/** @param {{cookies: any}} ctx @param {Record<string, any>} cuerpo */
export async function trasladar(ctx, cuerpo) {
  return apiRequest('/campo/inventario/traslados/', { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{cookies: any}} ctx */
export async function leerConteos(ctx) {
  try {
    const d = await apiRequest('/campo/inventario/conteos/', {}, ctx);
    return { conteos: d?.conteos ?? [], error: false };
  } catch {
    return { conteos: [], error: true };
  }
}

/** @param {{cookies: any}} ctx @param {string} ubicacion */
export async function abrirConteo(ctx, ubicacion) {
  return apiRequest('/campo/inventario/conteos/',
    { method: 'POST', body: { ubicacion } }, ctx);
}

/** @param {{cookies: any}} ctx @param {string} id @param {Record<string, any>} cuerpo */
export async function anotarConteo(ctx, id, cuerpo) {
  return apiRequest(`/campo/inventario/conteos/${id}/anotar/`,
    { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{cookies: any}} ctx @param {string} id */
export async function cerrarConteo(ctx, id) {
  return apiRequest(`/campo/inventario/conteos/${id}/cerrar/`,
    { method: 'POST', body: {} }, ctx);
}

/* ===========================================================================
 * FASE 3 -- proveedores, compras y valorización
 * =========================================================================== */

/** @param {{cookies: any}} ctx */
export async function leerProveedores(ctx) {
  try {
    const d = await apiRequest('/campo/inventario/proveedores/', {}, ctx);
    return { proveedores: d?.proveedores ?? [], error: false };
  } catch {
    return { proveedores: [], error: true };
  }
}

/** @param {{cookies: any}} ctx @param {Record<string, any>} cuerpo */
export async function crearProveedor(ctx, cuerpo) {
  return apiRequest('/campo/inventario/proveedores/', { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{cookies: any}} ctx @param {Record<string, any>} cuerpo */
export async function registrarCompra(ctx, cuerpo) {
  return apiRequest('/campo/inventario/compras/', { method: 'POST', body: cuerpo }, ctx);
}

/**
 * Cuánto vale lo que hay, y de qué no se sabe.
 *
 * `sin_costo_conocido` viaja tal cual hasta la pantalla: el total que el backend
 * calcula EXCLUYE lo que no puede valorizar, y esconder esa lista convertiría un
 * total incompleto en uno que parece completo.
 *
 * @param {{cookies: any}} ctx @param {string} ubicacion
 */
export async function leerValorizacion(ctx, ubicacion) {
  try {
    const d = await apiRequest(
      `/campo/inventario/valorizacion/?ubicacion=${encodeURIComponent(ubicacion)}`, {}, ctx
    );
    return { ...d, error: false };
  } catch {
    return { total: null, materiales: [], sin_costo_conocido: [], advertencia: '', error: true };
  }
}

/** @param {{cookies: any}} ctx @param {string} de */
export async function leerReporte(ctx, de, desde = '', hasta = '') {
  // El rango VIAJA, y antes no: la API ya aceptaba `desde` y `hasta` --los usa
  // para acotar el consumo-- y este cliente los ignoraba, asi que la pantalla
  // solo podia mostrar el acumulado de siempre. El filtro del diseno seria un
  // adorno sin esto.
  const q = new URLSearchParams({ de });
  if (desde) q.set('desde', desde);
  if (hasta) q.set('hasta', hasta);
  try {
    const d = await apiRequest(`/campo/inventario/reportes/?${q}`, {}, ctx);
    return { filas: d?.filas ?? [], error: false };
  } catch {
    return { filas: [], error: true };
  }
}

/**
 * Las plantillas de kit de la empresa, con sus líneas.
 *
 * @param {{cookies: any}} ctx
 * @param {boolean} todas incluir las desactivadas
 */
export async function leerPlantillas(ctx, todas = false) {
  try {
    const d = await apiRequest(
      `/campo/inventario/plantillas/${todas ? '?todas=1' : ''}`, {}, ctx
    );
    return { plantillas: d?.plantillas ?? [], error: false };
  } catch {
    return { plantillas: [], error: true };
  }
}

/**
 * Crea una plantilla.
 *
 * @param {{cookies: any}} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function crearPlantilla(ctx, cuerpo) {
  return apiRequest('/campo/inventario/plantillas/',
    { method: 'POST', body: cuerpo }, ctx);
}

/**
 * Reescribe una plantilla entera: nombre, descripción y líneas.
 *
 * @param {{cookies: any}} ctx
 * @param {string} id
 * @param {Record<string, any>} cuerpo
 */
export async function editarPlantilla(ctx, id, cuerpo) {
  return apiRequest(`/campo/inventario/plantillas/${id}/`,
    { method: 'PUT', body: cuerpo }, ctx);
}

/**
 * La deja de ofrecer. No la borra: sigue explicando despachos viejos.
 *
 * @param {{cookies: any}} ctx
 * @param {string} id
 */
export async function desactivarPlantilla(ctx, id) {
  return apiRequest(`/campo/inventario/plantillas/${id}/`,
    { method: 'DELETE' }, ctx);
}

/**
 * El catálogo COMPLETO, con los dados de baja y si cada uno ya tiene movimientos.
 *
 * Distinto de `leerCatalogo`, que sirve los desplegables y devuelve solo los
 * activos: acá se administra, así que hay que ver todo.
 *
 * @param {{cookies: any}} ctx
 */
export async function leerMateriales(ctx) {
  try {
    const d = await apiRequest('/campo/inventario/materiales/', {}, ctx);
    return { materiales: d?.materiales ?? [], error: false };
  } catch {
    return { materiales: [], error: true };
  }
}

/**
 * Da de alta un material.
 *
 * @param {{cookies: any}} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function crearMaterial(ctx, cuerpo) {
  return apiRequest('/campo/inventario/materiales/',
    { method: 'POST', body: cuerpo }, ctx);
}

/**
 * Corrige un material o lo da de baja. No hay borrado: ver la vista.
 *
 * @param {{cookies: any}} ctx
 * @param {string} id
 * @param {Record<string, any>} cuerpo
 */
export async function editarMaterial(ctx, id, cuerpo) {
  return apiRequest(`/campo/inventario/materiales/${id}/`,
    { method: 'PATCH', body: cuerpo }, ctx);
}

/**
 * Pone o reemplaza la foto de un material.
 *
 * `apiRequest` reconoce el FormData y deja que fetch ponga el boundary: por eso
 * el cuerpo va como FormData y no como objeto.
 *
 * @param {{cookies: any}} ctx
 * @param {string} id
 * @param {FormData} datos
 */
export async function subirImagenMaterial(ctx, id, datos) {
  return apiRequest(`/campo/inventario/materiales/${id}/imagen/`,
    { method: 'POST', body: datos }, ctx);
}

/**
 * Quita la foto. El material queda.
 *
 * @param {{cookies: any}} ctx
 * @param {string} id
 */
export async function quitarImagenMaterial(ctx, id) {
  return apiRequest(`/campo/inventario/materiales/${id}/imagen/`,
    { method: 'DELETE' }, ctx);
}
