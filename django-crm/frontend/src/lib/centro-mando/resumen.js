/**
 * Recortar un texto largo sin cortarlo a mitad de palabra.
 *
 * Existe por lo que pasa en la ficha de un agente: la "descripcion" de un
 * agente ES SU PROMPT. En Rapilink pasa de 2.000 caracteres y trae el
 * protocolo entero --cuando verificar identidad, que no prometer, como
 * derivar--. Volcado tal cual en la ficha tapaba los numeros, que es lo unico
 * que esa pantalla mide y que no se ve en ningun otro lado.
 *
 * Esta aqui y no dentro del componente por el mismo motivo que disposicion.js:
 * es calculo, tiene bordes (una sola frase larga, un punto demasiado temprano,
 * texto vacio) y dentro de un .svelte no se puede probar. El componente pinta;
 * esto decide.
 */

/** Cuanto se muestra antes de recortar. */
export const LIMITE_RESUMEN = 180;

/**
 * Donde cortar un punto es util. Por debajo de esta fraccion del limite,
 * cortar en el primer punto tira casi todo el texto -- pasa cuando la
 * descripcion arranca con una frase corta ("Atiende ventas.") y sigue con el
 * protocolo largo. En ese caso conviene cortar por palabra.
 */
const FRACCION_MINIMA = 0.4;

/**
 * Las primeras frases de un texto, cortadas donde termina una.
 *
 * Devuelve tambien SI recorto, y eso no es un detalle de implementacion: quien
 * lee tiene que saber que esta viendo un extracto. Un texto recortado en
 * silencio es una afirmacion falsa sobre lo que el agente hace.
 *
 * @param {string} texto
 * @returns {{ texto: string, recortado: boolean }}
 */
export function resumir(texto) {
  const limpio = (texto || '').trim();
  if (limpio.length <= LIMITE_RESUMEN) return { texto: limpio, recortado: false };

  const corte = limpio.slice(0, LIMITE_RESUMEN);

  // Se prefiere cortar donde termina una oracion. Ahi NO se agregan puntos
  // suspensivos: '.…' se lee como un error de tipeo, y la frase quedo cerrada.
  const punto = corte.lastIndexOf('. ');
  if (punto > LIMITE_RESUMEN * FRACCION_MINIMA) {
    return { texto: limpio.slice(0, punto + 1), recortado: true };
  }

  // Sin un punto util --una descripcion de una sola frase larga-- se corta por
  // palabra, y ahi los suspensivos si hacen falta: la frase queda abierta.
  const espacio = corte.lastIndexOf(' ');
  return {
    texto: limpio.slice(0, espacio > 0 ? espacio : LIMITE_RESUMEN).trim() + '…',
    recortado: true
  };
}
