/**
 * UNA PESTAÑA VIEJA NO SE QUEDA ROTA DESPUES DE UN DEPLOY.
 *
 * El caso, medido el 23/09/2026 en la consola de un operador: 404 de
 * `/_app/immutable/nodes/61.CyPCFAsf.js` y compania, y `TypeError: Failed to
 * fetch dynamically imported module`. La pestaña corria `app.zigMaWQl.js`, que
 * ya no existia en el servidor; el build vigente era otro y no referenciaba
 * ninguno de esos seis chunks. Causa: cinco deploys en 26 minutos.
 *
 * SvelteKit nombra cada archivo con un hash de su contenido, asi que un deploy
 * cambia los nombres y borra los viejos. Una pestaña abierta antes sigue
 * pidiendo los de su build cada vez que navega a una ruta que todavia no habia
 * cargado. `version.pollInterval` (svelte.config.js) pregunta cada minuto si
 * hay version nueva y hace navegacion dura en la siguiente, pero entre el
 * deploy y esa consulta hay una ventana, y ahi el operador ve la pantalla rota.
 *
 * Esto la cierra: el error de import dinamico se reconoce y se recarga UNA vez.
 *
 * POR QUE UNA VEZ Y NO SIEMPRE. Si el chunk falta por otro motivo --el
 * servidor sirviendo mal, una red que corta-- recargar en bucle deja al
 * operador con la pagina parpadeando y sin forma de leer el error. Con la
 * marca en sessionStorage, la segunda vez dentro de la ventana se deja pasar
 * el error para que se vea y se reporte.
 *
 * Modulo aparte de hooks.client.js para poder afirmarlo sin navegador: las dos
 * funciones son puras salvo por las dependencias que se le inyectan.
 */

/** Marca de la ultima recarga automatica. sessionStorage y no localStorage:
 *  muere con la pestaña, que es exactamente el alcance del problema. */
export const CLAVE_RECARGA = 'dexter:recarga-por-chunk-viejo';

/** Dos recargas mas juntas que esto son un bucle, no un deploy. */
export const VENTANA_MS = 10_000;

/**
 * Lo que dicen los navegadores cuando un import dinamico no se pudo traer.
 * Cada motor lo redacta distinto, y por eso son varios:
 *   Chrome/Edge  "Failed to fetch dynamically imported module: <url>"
 *   Firefox      "error loading dynamically imported module"
 *   Safari       "Importing a module script failed."
 *   Vite         "Unable to preload CSS for <url>"
 */
export const PATRON_CHUNK_VIEJO =
  /failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|unable to preload css|dynamically imported module.*(404|not found)/i;

/** Un error es de chunk viejo? Acepta el Error, su mensaje, o un evento. */
export function esChunkViejo(error) {
  if (!error) return false;
  const texto =
    typeof error === 'string'
      ? error
      : typeof error?.message === 'string'
        ? error.message
        : typeof error?.reason?.message === 'string'
          ? error.reason.message
          : '';
  return PATRON_CHUNK_VIEJO.test(texto);
}

/**
 * Recarga la pagina, salvo que ya se haya recargado hace menos de VENTANA_MS.
 * Devuelve si recargo, para que quien llama decida si ademas traga el error.
 *
 * Las dependencias se inyectan para poder probarlo; por defecto son las del
 * navegador. Si sessionStorage no esta disponible (pestaña privada, cookies
 * bloqueadas) no se recarga: sin marca no hay forma de evitar el bucle, y un
 * bucle es peor que una pantalla rota que el operador puede recargar a mano.
 */
export function recargarUnaVez({
  almacen = globalThis.sessionStorage,
  recargar = () => globalThis.location.reload(),
  ahora = Date.now()
} = {}) {
  try {
    if (!almacen) return false;
    const ultima = Number(almacen.getItem(CLAVE_RECARGA) || 0);
    if (Number.isFinite(ultima) && ahora - ultima < VENTANA_MS) return false;
    almacen.setItem(CLAVE_RECARGA, String(ahora));
    recargar();
    return true;
  } catch {
    return false;
  }
}

/**
 * Engancha la vigilancia en el navegador. Dos caminos, porque el error llega
 * por dos lados distintos:
 *
 *   vite:preloadError   lo dispara el ayudante de precarga de Vite cuando el
 *                       chunk no baja. Es el camino normal al navegar, y llega
 *                       ANTES de que el error se propague: si recargamos,
 *                       preventDefault() evita que ademas se reporte.
 *   unhandledrejection  el import que revienta fuera de una navegacion (por
 *                       ejemplo un componente que se carga solo).
 *
 * El tercer camino --el `handleError` de SvelteKit-- se engancha en
 * hooks.client.js, que es donde ese hook vive.
 *
 * No hace nada fuera del navegador (SSR, pruebas en node).
 */
export function vigilarChunksViejos(ventana = globalThis) {
  if (!ventana || typeof ventana.addEventListener !== 'function') return false;
  ventana.addEventListener('vite:preloadError', (evento) => {
    if (recargarUnaVez()) evento.preventDefault?.();
  });
  ventana.addEventListener('unhandledrejection', (evento) => {
    if (esChunkViejo(evento?.reason)) recargarUnaVez();
  });
  return true;
}
