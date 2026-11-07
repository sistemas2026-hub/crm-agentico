/**
 * AFINAR LA INSTRUCCIÓN DE UNA FOTO, DESDE DONDE SE DESCUBRE QUE ESTÁ MAL
 * =======================================================================
 *
 * El usuario, el 06/11/2026, después de ver cuatro fotos marcadas «no es lo
 * que se pidió»: *"hagámoslo más fácil, que uno le indique por texto así como
 * ahora y guarde eso"*.
 *
 * La instrucción de cada foto —«Tenía que mostrar: Pantalla del medidor con la
 * lectura legible»— se editaba a ciegas en otra pantalla, y había que esperar a
 * que una orden NUEVA la usara para saber si servía. Acá se prueba contra la
 * foto que ya falló y recién después se guarda.
 *
 * POR QUÉ ESTE ARCHIVO Y NO EL `.svelte`
 * ---------------------------------------
 * Misma razón que `components/manual/entrenar.js`, y está medida: el harness
 * (`vitest.config.js`) **no compila `.svelte`**. Lo que viva dentro de un
 * componente no se puede probar, y decir que está probado porque «la pantalla
 * se ve bien» es exactamente lo que el método prohíbe.
 *
 * Las funciones de acá son puras: entran datos, salen datos.
 */

/** El mismo tope que `plantillas.MAX_TEXTO_LARGO` y que la ruta del backend. */
export const MAX_INSTRUCCION = 400;

/**
 * Si el texto se puede mandar a probar, o por qué no.
 *
 * SE VALIDA ANTES DE PEDIR porque cada prueba cuesta una llamada al modelo,
 * que se cobra. Gastarla para que el backend conteste 400 es tirar plata; y
 * aprobar un texto más largo del que la plantilla admite sería aprobar algo
 * que después no se puede guardar.
 *
 * @param {string} texto
 * @param {string} guardado lo que la plantilla tiene hoy
 * @returns {{puede: boolean, motivo: string}}
 */
export function sePuedeProbar(texto, guardado = '') {
  const limpio = (texto || '').trim();
  if (!limpio) return { puede: false, motivo: 'Escribí qué tenía que mostrar la foto.' };
  if (limpio.length > MAX_INSTRUCCION) {
    return {
      puede: false,
      motivo: `Son ${limpio.length} caracteres y el campo admite ${MAX_INSTRUCCION}.`
    };
  }
  if (limpio === (guardado || '').trim()) {
    //  No es un error: es que no hay nada nuevo que medir. Probar lo mismo
    //  otra vez gasta una llamada para repetir el resultado que ya está arriba.
    return { puede: false, motivo: 'Es el texto que ya está guardado.' };
  }
  return { puede: true, motivo: '' };
}

/**
 * Cómo se lee el veredicto del modelo, en palabras.
 *
 * TRES VALORES, NO DOS. `null` es «no se sabe», y es distinto de «no
 * corresponde»: el 06/11/2026 un parser binario leyó «MUESTRA: no se sabe»
 * como un «no» y produjo un veredicto falso. Mostrar una duda como un rechazo
 * mandaría a alguien a reescribir una instrucción que estaba bien.
 *
 * @param {boolean|null|undefined} corresponde
 * @returns {{icono: string, texto: string, clase: string}}
 */
export function veredicto(corresponde) {
  if (corresponde === true) {
    return { icono: '✓', texto: 'Con este texto, la foto SÍ muestra lo que se pide.', clase: 'ok' };
  }
  if (corresponde === false) {
    return { icono: '✗', texto: 'Con este texto, la foto NO muestra lo que se pide.', clase: 'no' };
  }
  return {
    icono: '?',
    texto: 'Con este texto, el modelo no puede afirmar si la foto corresponde.',
    clase: 'duda'
  };
}

/**
 * Qué conviene hacer con el resultado de una prueba.
 *
 * NO DECIDE POR LA PERSONA: sugiere. Un `✓` sobre UNA foto no prueba que la
 * redacción sirva para todas —puede estar aprobando por casualidad— y un `✗`
 * puede ser una foto genuinamente mala, no una instrucción mala. Por eso el
 * texto dice qué significa, no qué hacer.
 *
 * @param {boolean|null|undefined} corresponde
 * @param {boolean} fotoEstaBien lo que la persona ya sabe de ESA foto
 * @returns {string}
 */
export function queSignifica(corresponde, fotoEstaBien) {
  if (fotoEstaBien && corresponde === true) {
    return 'La foto estaba bien y ahora se lee bien: el texto anterior era el problema.';
  }
  if (fotoEstaBien && corresponde !== true) {
    return 'Vos decís que la foto está bien y el modelo sigue sin verlo: probá otra redacción, más concreta sobre qué número o elemento tiene que verse.';
  }
  if (!fotoEstaBien && corresponde === true) {
    return 'Ojo: la foto no era la correcta y con este texto igual la aprueba. El texto quedó demasiado laxo.';
  }
  return 'La foto no era la correcta y el texto lo detecta. Eso es lo que se busca.';
}

/**
 * El cuerpo del pedido de prueba.
 * @param {string} texto
 * @returns {{instrucciones: string}}
 */
export function cuerpoDePrueba(texto) {
  return { instrucciones: (texto || '').trim() };
}
