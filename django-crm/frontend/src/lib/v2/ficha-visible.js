/**
 * Cómo se dibuja un campo de la ficha que quien mira no puede ver  --  12/11/2026
 *
 * La ficha llega ya filtrada por el motor (nucleo/seguridad/ficha_por_area.py)
 * con `_ocultos`: los campos que esta persona no ve. Un campo oculto se dice
 * «oculto para tu área», nunca se deja en blanco: un renglón vacío afirma que
 * el cliente no tiene ese dato, y eso es mentira.
 */

export const TEXTO_OCULTO = 'Oculto para tu área';

/**
 * @param {any} ficha
 * @param {string} campo
 */
export function estaOculto(ficha, campo) {
  if (!ficha) return false;
  if (ficha._sinCriterio) return true;
  return Array.isArray(ficha._ocultos) && ficha._ocultos.includes(campo);
}

/**
 * Si el campo tiene algo que mostrar: su valor, o el aviso de que está oculto.
 * @param {any} ficha
 * @param {string} campo
 */
export function hayQueMostrar(ficha, campo) {
  return !!ficha?.[campo] || estaOculto(ficha, campo);
}
