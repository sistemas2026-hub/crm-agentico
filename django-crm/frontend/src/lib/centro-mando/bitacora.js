/**
 * DOS HISTORIALES, EN DOS SITIOS DISTINTOS.
 *
 * El prototipo necesita moverse sin backend —si no, no hay nada que mirar— y
 * eso obliga a generar actividad de demostración. El riesgo es obvio y es el
 * que figura como grave en la ficha: **un movimiento inventado contado como
 * trabajo real**.
 *
 * La protección NO es una bandera. Una bandera se lee con un `if` y el día que
 * alguien escriba `historial.push(...)` sin consultarla, lo simulado entra y no
 * se nota: parece un historial normal. Acá hay **dos arreglos separados** y la
 * única forma de escribir en ellos es `anotar()`, que mira la procedencia. Para
 * que un dato simulado acabe en el historial real haría falta cambiar esta
 * función, no olvidarse de un `if`.
 *
 * Y la pantalla muestra uno o el otro, nunca la unión: concatenarlos para
 * «verlo todo junto» es exactamente la mezcla que esto existe para impedir.
 */

import { esReal, esSimulado } from './escena/adaptador';

/** Cuántas anotaciones se guardan. Más que esto nadie lee, y la lista crece sin
 *  tope en una pantalla que puede quedarse abierta todo el día. */
const MAXIMO = 60;

/**
 * @typedef {{ id: string, agente: string, tipo: string, etiqueta: string|null,
 *             procedencia: string, en: string|null, visto: number }} Anotacion
 */

export function crearBitacora(maximo = MAXIMO) {
  /** @type {Anotacion[]} */
  let real = [];
  /** @type {Anotacion[]} */
  let simulado = [];
  /** Instrucciones cuya procedencia no es ninguna de las dos reconocidas. */
  let descartadas = 0;
  const vistos = new Set();

  /**
   * Anota instrucciones ya proyectadas.
   *
   * @param {any[]} instrucciones las que devolvió `proyectar()`
   */
  function anotar(instrucciones) {
    for (const i of instrucciones || []) {
      if (!i || !i.id || !i.procedencia) {
        descartadas++;
        continue;
      }
      // Una instrucción entra una sola vez aunque el flujo la entregue dos
      // veces: duplicar es el precio de no perder ninguna, y un historial con
      // la misma línea repetida se lee como dos hechos.
      const clave = `${i.procedencia}|${i.id}`;
      if (vistos.has(clave)) continue;
      vistos.add(clave);

      const anotacion = {
        id: i.id,
        agente: i.agente,
        tipo: i.tipo,
        etiqueta: i.etiqueta ?? null,
        procedencia: i.procedencia,
        en: i.en ?? null,
        visto: Date.now()
      };

      if (esReal(i.procedencia)) real = [anotacion, ...real].slice(0, maximo);
      else if (esSimulado(i.procedencia)) simulado = [anotacion, ...simulado].slice(0, maximo);
      // Lo decorativo (`ambiente`) no tiene historial: no pasó nada. Contarlo
      // como actividad es justo la afirmación que no se puede hacer.
      else descartadas++;
    }
  }

  return {
    anotar,
    /** El historial de hechos registrados. Nunca contiene nada simulado. */
    get real() {
      return real;
    },
    /** El de la demostración. Vive aparte y se rotula como tal en pantalla. */
    get simulado() {
      return simulado;
    },
    get descartadas() {
      return descartadas;
    },
    /** Borra solo el de demostración: al apagar la demostración, lo real sigue. */
    olvidarSimulado() {
      simulado = [];
    }
  };
}
