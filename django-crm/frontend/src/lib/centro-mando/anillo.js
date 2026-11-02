/**
 * LA SEDE COMO DOS MANZANAS CON UN PATIO EN EL MEDIO.
 *
 * Una manzana de departamentos a la izquierda, otra a la derecha, el patio
 * entre las dos y la entrada al frente del patio. Cada sala conserva su tamaño
 * natural y se pega a la siguiente a lo largo de su columna, así que los muros
 * se comparten sin estirar nada.
 *
 * POR QUÉ NO ES UNA REJILLA DE CELDAS
 * -----------------------------------
 * `planta-unica.js` pone cada sala en una celda de tamaño fijo, y eso se probó
 * en el navegador de las dos formas posibles. Las dos fallaron:
 *
 * - **Estirando la sala hasta llenar la celda**: todas quedaban del mismo
 *   tamaño —se perdía que el NOC es ancho y Dirección chica— y cada una
 *   arrastraba un halo de suelo pelado.
 * - **Dejándola en su tamaño real**: se tocaban solo donde la celda coincidía
 *   y el resto quedaba suelto, como islas en un descampado.
 *
 * El error era la rejilla: una sede **embaldosa**, no reparte casilleros.
 *
 * EL HUECO QUE COSTÓ UNA REVISIÓN, Y DÓNDE ESTABA DE VERDAD
 * ---------------------------------------------------------
 * La primera versión repartía las salas **alternando** —una a cada manzana— y
 * cortaba las columnas cada cinco salas. Con once departamentos eso daba seis
 * a la izquierda y cinco a la derecha, y la sexta se llevaba **una columna
 * entera para ella sola**: 13 × 48 de columna para una sala de 13 × 9. Medido:
 * **507 unidades de suelo vacío pegadas al patio**, más otras tantas por la
 * diferencia de fondo entre las dos manzanas.
 *
 * Eso es lo que se leía como «el centro de la empresa es un enorme espacio
 * vacío». El patio ocupaba 640 —el 24%— y a su lado había un hueco casi igual
 * de grande que no era patio ni era nada. Juntos, una franja vacía continua de
 * punta a punta. Las salas ocupaban el **47% del suelo**.
 *
 * Dos cambios, y los dos salen de la medición y no del gusto:
 *
 * 1. **El reparto se equilibra por FONDO ACUMULADO**, no alternando. A cada
 *    sala le toca la manzana menos honda hasta ese momento. Alternar es el
 *    caso particular en que todas las salas miden lo mismo —y no lo miden—.
 *    Sigue siendo estable en el sentido que importa: agregar la sala número 12
 *    no mueve a las once anteriores, porque la decisión de cada una solo mira
 *    lo que había antes que ella.
 * 2. **Las columnas se cortan por FONDO, no por cuenta.** Cinco salas era un
 *    número fijo que no sabía si eran chicas o grandes.
 *
 * Resultado sobre la empresa del piloto: **68 × 28, las salas ocupan el 67%**
 * y el suelo muerto baja de 644 a 180.
 *
 * @see fondoObjetivo para de dónde sale el corte, que es la parte con trampa.
 */

/** La franja del frente del patio: por donde se entra. */
export const ENTRADA = { fondo: 8 };

/** El pasillo entre las salas y el patio. */
export const PASILLO = 4;

/** Lo mínimo que mide el patio, aunque las manzanas sean cortas. */
export const PATIO_MINIMO = { ancho: 14, fondo: 10 };

const medida = (s) => s?.planta?.mundo ?? { ancho: 10, fondo: 8 };

/**
 * Las dos manzanas, equilibradas por fondo acumulado.
 *
 * ESTABLE A PROPÓSITO. Cada sala mira solo lo que se repartió ANTES que ella,
 * así que sumar un departamento al final no reubica a ninguno de los que ya
 * estaban. Repartir «la primera mitad a la izquierda» no tiene esa propiedad:
 * con once salas la mitad cae en otro sitio que con doce y medio edificio
 * cambia de manzana al sumar una.
 *
 * @param {any[]} lista
 */
export function repartirManzanas(lista) {
  const izquierda = [];
  const derecha = [];
  let fi = 0;
  let fd = 0;
  for (const sala of lista) {
    if (fi <= fd) {
      izquierda.push(sala);
      fi += medida(sala).fondo;
    } else {
      derecha.push(sala);
      fd += medida(sala).fondo;
    }
  }
  return { izquierda, derecha };
}

/**
 * Las columnas de una manzana: se abre una nueva cuando la siguiente sala
 * pasaría el fondo objetivo.
 *
 * @param {any[]} grupo
 * @param {number} objetivo
 */
export function columnasHasta(grupo, objetivo) {
  const columnas = [];
  let actual = [];
  let fondo = 0;
  for (const sala of grupo) {
    const f = medida(sala).fondo;
    if (actual.length > 0 && fondo + f > objetivo) {
      columnas.push(actual);
      actual = [];
      fondo = 0;
    }
    actual.push(sala);
    fondo += f;
  }
  if (actual.length > 0) columnas.push(actual);
  return columnas;
}

/** La forma de una manzana: sus columnas, su ancho y su fondo. */
function formaDe(grupo, objetivo) {
  const columnas = columnasHasta(grupo, objetivo);
  return {
    columnas,
    ancho: columnas.reduce(
      (t, c) => t + c.reduce((m, s) => Math.max(m, medida(s).ancho), 0), 0),
    fondo: columnas.reduce(
      (m, c) => Math.max(m, c.reduce((t, s) => t + medida(s).fondo, 0)), 0)
  };
}

/** El plano que sale de un fondo objetivo, con sus dos cifras de calidad. */
function planoCon(lista, objetivo) {
  const { izquierda, derecha } = repartirManzanas(lista);
  const izq = formaDe(izquierda, objetivo);
  const der = formaDe(derecha, objetivo);
  const fondo = Math.max(izq.fondo, der.fondo, PATIO_MINIMO.fondo);
  const anchoPatio = Math.max(
    PATIO_MINIMO.ancho, Math.round((izq.ancho + der.ancho) * 0.3));
  const ancho = izq.ancho + anchoPatio + der.ancho;
  const areaSalas = lista.reduce(
    (t, s) => t + medida(s).ancho * medida(s).fondo, 0);
  return {
    izq, der, fondo, anchoPatio, ancho, areaSalas,
    //  Suelo dentro de las manzanas que no es sala. El patio NO cuenta: el
    //  patio tiene que estar, el hueco al lado de una columna no.
    muerto: izq.ancho * fondo + der.ancho * fondo - areaSalas,
    //  CUÁNTA OFICINA ENTRA EN PANTALLA. Ver `fondoObjetivo`.
    enPantalla: 2 * areaSalas / ((ancho + fondo) ** 2)
  };
}

/**
 * El fondo al que se cortan las columnas, y por qué ese número.
 *
 * SE BARREN TODOS Y SE ELIGE POR UNA CIFRA MEDIBLE: cuánta oficina entra en
 * pantalla. Y esa cifra sale de la proyección, no de un gusto.
 *
 * En esta isometría `aPantalla(gx, gy)` manda la planta a
 * `x = (gx − gy)·32`, `y = (gx + gy)·16`. Dos consecuencias que no son obvias:
 *
 * - La caja que ocupa el plano en pantalla mide `(ancho + fondo)·32` por
 *   `(ancho + fondo)·16`: **siempre 2:1, cualquiera sea la forma del plano**.
 *   Un plano más ancho que hondo NO aprovecha mejor una pantalla apaisada,
 *   que es lo que yo había supuesto antes de hacer la cuenta.
 * - Lo único que decide cuánta de esa caja es oficina es
 *   `2 · área de salas / (ancho + fondo)²`.
 *
 * Entonces el criterio es maximizar esa fracción, que es exactamente «que se
 * vea la mayor cantidad de oficina posible». Y se sostiene solo: un plano
 * degenerado de una sala de fondo —177 × 10, que deja casi cero suelo muerto y
 * parece ganador si uno mira solo el desperdicio— cae al **7,3%** de pantalla
 * contra el 27,7% del elegido. No hace falta prohibirlo: pierde.
 *
 * El desempate, cuando dos cortes dan la misma pantalla, es menos suelo
 * muerto. Pasa de verdad: sobre el piloto, 68 × 28 y 41 × 55 empatan en 27,7%
 * y el segundo deja las manzanas de una sola columna de grosor —la cinta flaca
 * que este archivo ya había rechazado una vez—.
 *
 * LÍMITE CONOCIDO, medido y no escondido: para algunos tamaños de empresa el
 * ganador es un plano hondo. Con catorce salas sale 41 × 67, y ahí el patio
 * mide 14 × 67 y se lee como un callejón. La cifra de pantalla no distingue un
 * patio de un pasillo largo porque solo mira el área de las salas.
 *
 * @param {any[]} lista
 */
export function fondoObjetivo(lista) {
  const fondos = lista.map((s) => medida(s).fondo);
  const minimo = Math.max(...fondos);
  const maximo = fondos.reduce((a, b) => a + b, 0);
  let mejor = null;
  let elegido = minimo;
  for (let o = minimo; o <= maximo; o++) {
    const p = planoCon(lista, o);
    const gana = mejor === null
      || p.enPantalla > mejor.enPantalla
      || (p.enPantalla === mejor.enPantalla && p.muerto < mejor.muerto);
    if (gana) {
      mejor = p;
      elegido = o;
    }
  }
  return elegido;
}

/**
 * La sede: dos manzanas macizas con un patio en el medio.
 *
 * @param {any[]} salas las salas compuestas de la empresa
 */
export function repartirAnillo(salas) {
  const lista = (Array.isArray(salas) ? salas : []).filter(Boolean);
  if (lista.length === 0) {
    return {
      puestas: [],
      huella: { ancho: PATIO_MINIMO.ancho, fondo: PATIO_MINIMO.fondo },
      patio: null,
      entrada: {
        x: 0,
        y: Math.max(0, PATIO_MINIMO.fondo - ENTRADA.fondo),
        ancho: PATIO_MINIMO.ancho,
        fondo: Math.min(ENTRADA.fondo, PATIO_MINIMO.fondo)
      }
    };
  }

  const objetivo = fondoObjetivo(lista);
  const { izq, der, fondo, anchoPatio, ancho } = planoCon(lista, objetivo);

  //  LA ENTRADA VA DENTRO, NO COLGANDO DEL FRENTE.
  //
  //  La primera versión sumaba su fondo a la huella, y eso estiraba el
  //  edificio por debajo de las dos manzanas: una franja de 52 × 16 de suelo
  //  pelado que no era entrada ni era nada, el 25% del plano. Medido. El
  //  edificio llega hasta donde llegan las manzanas, y la entrada es el tramo
  //  del frente del patio.
  const huella = { ancho, fondo };

  const puestas = [];
  const colocar = (forma, x0, banda) => {
    let x = x0;
    for (const columna of forma.columnas) {
      const anchoCol = columna.reduce((m, s) => Math.max(m, medida(s).ancho), 0);
      let y = 0;
      for (const sala of columna) {
        const m = medida(sala);
        puestas.push({ sala, x, y, ancho: m.ancho, fondo: m.fondo, banda });
        y += m.fondo;
      }
      x += anchoCol;
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
      fondo: Math.max(0, fondo - ENTRADA.fondo)
    },
    entrada: {
      x: izq.ancho,
      y: Math.max(0, fondo - ENTRADA.fondo),
      ancho: anchoPatio,
      fondo: Math.min(ENTRADA.fondo, fondo)
    }
  };
}
