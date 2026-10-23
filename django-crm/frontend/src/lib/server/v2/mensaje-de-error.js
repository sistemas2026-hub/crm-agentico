/**
 * El motivo de un fallo, dicho como lo explicó el backend.
 *
 * POR QUÉ ESTO EXISTE  --  13/10/2026
 *
 * Había tres copias de esta función y **ninguna leía donde el dato está**.
 * `apiRequest` (`$lib/api-helpers.js:135`) lanza un `Error` al que le cuelga
 * `.status` y **`.body`** —el JSON del error, ya parseado—. Nada más:
 *
 *   despacho/+page.server.js    leía `e.data.detalle` y `e.data.error`
 *                               -> `e.data` es SIEMPRE undefined
 *   cuadrillas/+page.server.js  leía `e.body.detail`
 *   inventario/+page.server.js  leía `e.body.detail`
 *
 * Y el backend de campo responde `{"error": "<CODIGO>", "detalle": "<frase>"}`
 * (`campo/despacho_views.py`, veinte sitios). O sea:
 *
 *   - Despacho caía a `e.message`, que `api-helpers` arma con `errorData.error`
 *     cuando no hay `detail`: la persona leía **`NO_SE_PUDO_CREAR`** o
 *     **`VALIDACION_INVALIDA`** en la pantalla, y la frase que explica qué
 *     hacer --«La orden ya está programada para esa fecha»-- no salía nunca.
 *   - Las otras dos buscaban `detail` (DRF) y se perdían `detalle` (campo).
 *
 * El orden de abajo no es arbitrario: **`detalle` primero porque es la frase
 * para una persona**, y `error` al final porque es un código para una máquina.
 * Mostrar el código cuando existe la frase es elegir el peor de los dos.
 *
 * @param {any} e El error que lanzó `apiRequest`.
 * @param {string} porDefecto Qué decir cuando el backend no explicó nada.
 */
export function mensajeDeError(e, porDefecto = 'No se pudo completar la operación.') {
  const cuerpo = e?.body ?? {};
  const candidatos = [
    cuerpo.detalle,          // la frase de los endpoints de campo
    cuerpo.detail,           // la de DRF
    e?.detail,
    typeof cuerpo.error === 'string' ? cuerpo.error : null,
    e?.message
  ];

  for (const c of candidatos) {
    if (typeof c !== 'string') continue;
    //  `Error 400: ` y `HTTP 500: Internal Server Error` son ruido del
    //  transporte, no el motivo. Se sacan en vez de mostrarlos: quien lee la
    //  pantalla no puede hacer nada con un número.
    const limpio = c.replace(/^(Error|HTTP) \d+:\s*/, '').trim();
    if (limpio) return limpio;
  }
  return porDefecto;
}
