/**
 * LA SEDE COMO ANILLO: bandas de salas alrededor de un patio.
 *
 * Es la composición de la referencia aprobada, leída como plano: una columna
 * de departamentos a la izquierda, una franja al fondo, otra columna a la
 * derecha, el patio en el medio y la entrada al frente con la recepción. Entre
 * las salas y el patio queda un pasillo que las recorre.
 *
 * POR QUÉ SE ABANDONÓ LA REJILLA DE CELDAS
 * ----------------------------------------
 * `planta-unica.js` pone cada sala en una celda de tamaño fijo, y eso se probó
 * en el navegador de las dos formas posibles. Las dos fallaron, y por el mismo
 * motivo de fondo:
 *
 * - **Estirando la sala hasta llenar la celda**: todas quedaban del mismo
 *   tamaño —se perdía que el NOC es ancho y Dirección chica— y cada una
 *   arrastraba un halo de suelo pelado, porque el mobiliario de una plantilla
 *   de 13 × 9 quedaba centrado en una sala de 21 × 13.
 * - **Dejándola en su tamaño real**: se tocaban solo donde la celda coincidía
 *   y el resto quedaba suelto, como islas en un descampado.
 *
 * El error era la rejilla: una sede **embaldosa**, no reparte casilleros. Acá
 * cada sala conserva su tamaño natural y se pega a la siguiente a lo largo de
 * su banda, así que los muros se comparten sin estirar nada.
 *
 * QUÉ SE PIERDE, Y HAY QUE DECIRLO
 * --------------------------------
 * La rejilla de celdas tenía una propiedad medida y valiosa: agregar un
 * departamento movía **cero** de los que ya estaban. Un anillo no puede dar
 * eso entero —el grosor de una banda sale de la sala más ancha que tiene, y la
 * posición de la banda derecha depende del ancho total—. Lo que sí da está
 * medido en `anillo.test.js`: un departamento nuevo mueve **solo su banda**,
 * no la oficina.
 */

/** La franja del frente: por donde se entra, y donde va la recepción. */
export const ENTRADA = { fondo: 8 };

/** El pasillo entre las salas y el patio. */
export const PASILLO = 4;

/** Lo mínimo que mide el patio, aunque las bandas sean cortas. */
export const PATIO_MINIMO = { ancho: 16, fondo: 10 };

/**
 * Cuántas salas seguidas van en una corrida antes de doblar hacia adentro.
 *
 * EL ANILLO TIENE QUE TENER GROSOR. La primera versión ponía cada banda en una
 * sola fila, y con once departamentos repartidos de a cuatro el anillo quedaba
 * de UNA sala de grosor: el patio se comía la mitad de la sede y las oficinas
 * eran una cinta flaca en el borde. En la referencia aprobada el bloque de la
 * derecha tiene DOS salas de fondo, y por eso el patio es un patio y no un
 * descampado.
 *
 * CINCO, Y SALE DE UN BARRIDO, NO DE UN GUSTO. Se midieron las combinaciones
 * de corrida, entrada y patio mínimo sobre la empresa del piloto, mirando dos
 * cifras a la vez: cuánto del suelo ocupan las salas y cuán cuadrada queda la
 * planta. Con cuatro: 68 × 39, ocupación 48%, esbeltez 1,74 —ancha—. Con seis:
 * 43 × 57, ocupación 52% pero esbeltez 0,75 —un pasillo hondo—. Con cinco:
 * **56 × 48, ocupación 47%, esbeltez 1,17**, que es la única que sale
 * razonable en las dos.
 */
export const CORRIDA = 5;

/** Las tres bandas, en el orden en que se reparten las salas. */
export const BANDAS = ['izquierda', 'fondo', 'derecha'];

const medida = (s) => s?.planta?.mundo ?? { ancho: 10, fondo: 8 };

/**
 * A qué manzana va la sala número `i`: izquierda o derecha.
 *
 * ALTERNANDO, Y NO POR MITADES. Repartir «las primeras a la izquierda, las
 * demás a la derecha» parece más ordenado y es inestable: con once
 * departamentos la mitad cae en otro sitio que con doce, y medio edificio
 * cambia de manzana al sumar uno. Alternando, la sala número 5 está en la
 * misma manzana para siempre.
 *
 * @param {number} i
 */
export function bandaDe(i) {
  return Math.max(0, Math.trunc(i)) % 2 === 0 ? 'izquierda' : 'derecha';
}

/** Las salas de una manzana, repartidas en columnas de `CORRIDA` salas. */
function columnasDe(grupo) {
  const salida = [];
  for (let i = 0; i < grupo.length; i += CORRIDA) salida.push(grupo.slice(i, i + CORRIDA));
  return salida;
}

/**
 * La sede: dos manzanas macizas con un patio en el medio.
 *
 * POR QUÉ DOS MANZANAS Y NO UN ANILLO. Se construyó primero como anillo
 * —columna, franja al fondo, columna— y se midió: las salas ocupaban el **27%
 * del suelo**, con el resto repartido entre patio, pasillos y una explanada de
 * entrada más grande que los once departamentos juntos. Un anillo de once
 * salas encierra demasiado: para que el anillo sea grueso harían falta veinte.
 *
 * La referencia aprobada no es un anillo tampoco, aunque lo parezca: es un
 * bloque de tres salas a la izquierda, uno de seis a la derecha y el patio
 * entre los dos. Macizos. Eso es lo que se dibuja acá.
 *
 * @param {any[]} salas las salas compuestas de la empresa
 */
export function repartirAnillo(salas) {
  const lista = (Array.isArray(salas) ? salas : []).filter(Boolean);
  if (lista.length === 0) {
    return {
      puestas: [],
      huella: { ancho: PATIO_MINIMO.ancho, fondo: PATIO_MINIMO.fondo + ENTRADA.fondo },
      patio: null,
      entrada: { x: 0, y: PATIO_MINIMO.fondo, ancho: PATIO_MINIMO.ancho, fondo: ENTRADA.fondo }
    };
  }

  const manzanas = { izquierda: [], derecha: [] };
  lista.forEach((sala, i) => manzanas[bandaDe(i)].push(sala));

  //  La forma de una manzana: columnas de salas pegadas, cada columna tan
  //  ancha como su sala mayor.
  const formaDe = (grupo) => {
    const cols = columnasDe(grupo);
    return {
      cols,
      ancho: cols.reduce((t, c) => t + c.reduce((m, s) => Math.max(m, medida(s).ancho), 0), 0),
      fondo: cols.reduce((m, c) => Math.max(m, c.reduce((t, s) => t + medida(s).fondo, 0)), 0)
    };
  };
  const izq = formaDe(manzanas.izquierda);
  const der = formaDe(manzanas.derecha);

  const fondoManzanas = Math.max(izq.fondo, der.fondo, PATIO_MINIMO.fondo);
  const anchoPatio = Math.max(PATIO_MINIMO.ancho, Math.round((izq.ancho + der.ancho) * 0.3));

  //  LA ENTRADA VA DENTRO, NO COLGANDO DEL FRENTE.
  //
  //  La primera versión sumaba su fondo a la huella, y eso estiraba el
  //  edificio por debajo de las dos manzanas: una franja de 52 × 16 de suelo
  //  pelado que no era entrada ni era nada, el 25% del plano. Medido. El
  //  edificio llega hasta donde llegan las manzanas, y la entrada es el tramo
  //  del frente del patio.
  const huella = {
    ancho: izq.ancho + anchoPatio + der.ancho,
    fondo: fondoManzanas
  };

  const puestas = [];
  const colocar = (forma, x0, banda) => {
    let x = x0;
    for (const col of forma.cols) {
      const ancho = col.reduce((m, s) => Math.max(m, medida(s).ancho), 0);
      let y = 0;
      for (const sala of col) {
        const m = medida(sala);
        puestas.push({ sala, x, y, ancho: m.ancho, fondo: m.fondo, banda });
        y += m.fondo;
      }
      x += ancho;
    }
  };
  colocar(izq, 0, 'izquierda');
  colocar(der, izq.ancho + anchoPatio, 'derecha');

  //  El orden de salida es el de entrada: quien dibuja y quien prueba esperan
  //  que la sala número 3 sea la tercera, no la tercera de su manzana.
  const porSala = new Map(puestas.map((p) => [p.sala, p]));
  const ordenadas = lista.map((s) => porSala.get(s)).filter(Boolean);

  return {
    puestas: ordenadas,
    huella,
    patio: {
      x: izq.ancho,
      y: 0,
      ancho: anchoPatio,
      fondo: Math.max(0, fondoManzanas - ENTRADA.fondo)
    },
    entrada: {
      x: izq.ancho,
      y: Math.max(0, fondoManzanas - ENTRADA.fondo),
      ancho: anchoPatio,
      fondo: Math.min(ENTRADA.fondo, fondoManzanas)
    }
  };
}
