/**
 * LA SEDE EN UNA SOLA PLANTA, Y QUE NO SE MUEVA CUANDO LA EMPRESA CRECE.
 *
 * Dos decisiones de producto del 01/11/2026, las dos con su motivo:
 *
 * 1. **Todos los departamentos en una planta.** No hay pisos apilados: se
 *    navega trasladándose hacia el departamento, no cambiando de nivel. Con
 *    eso desaparece de un plumazo toda la aritmética de oclusión —la losa de
 *    arriba, la cubierta, los 38 de altura de piso— porque ya no hay nada
 *    encima de nada.
 * 2. **Una empresa crea más agentes a medida que crece**, y cada empresa tiene
 *    los suyos. Así que la planta no puede estar dibujada: tiene que ser una
 *    función del dato.
 *
 * EL PROBLEMA QUE ESTE ARCHIVO RESUELVE, Y QUE SE MIDIÓ ANTES DE ESCRIBIRLO
 * ------------------------------------------------------------------------
 * `repartirPiso` elige las columnas con `round(sqrt(n·0,85))`, y eso cambia al
 * cruzar un umbral. Medido agregando UN departamento:
 *
 *      7 →  8:   5 de  7 salas cambian de lugar
 *     14 → 15:  11 de 14 cambian de lugar
 *     23 → 24:  19 de 23 cambian de lugar
 *
 * La empresa suma un departamento y media oficina se muda. Eso no es un
 * detalle estético: una oficina virtual sirve porque uno se acuerda de dónde
 * están las cosas, y la que se reacomoda sola deja de ser un lugar.
 *
 * CÓMO SE RESUELVE: CELDAS FIJAS Y UN ORDEN QUE SOLO AGREGA
 * ---------------------------------------------------------
 * Dos propiedades no se pueden tener a la vez con una rejilla que se recalcula:
 * **mantenerse cuadrada** y **no mover nada al agregar**. Acá se consiguen las
 * dos cambiando lo que se recalcula:
 *
 * - La **celda es constante**, no «el ancho de la sala más ancha de su
 *   columna». Si dependiera del contenido, ampliar una sala correría todas las
 *   de su derecha. Lo que sobra alrededor de una sala chica no es desperdicio:
 *   es la circulación de una planta abierta, que es exactamente lo que tiene la
 *   referencia aprobada.
 * - El **orden de las celdas crece en L**: se completa el cuadrado y recién
 *   entonces se abre una columna o una fila nueva. `celdaDe(i)` es una función
 *   pura de `i`, así que la sala número 3 está en la misma celda para siempre,
 *   tenga la empresa cuatro departamentos o cuarenta.
 *
 * La consecuencia se mide y no se argumenta: agregar un departamento mueve
 * **cero** de los que ya estaban, para cualquier cantidad. Está en
 * `planta-unica.test.js`.
 */

/**
 * La celda: constante, y por eso el tamaño de la sala más grande que
 * `plantillaPara()` puede construir, más la circulación que la rodea.
 *
 * Se mide con `tecnica_25`, que es 33,8 × 14,4 — la más grande de las que el
 * catálogo sabe derivar. Si algún día hiciera falta una mayor, este número es
 * lo único que hay que mover, y moverlo recoloca la planta entera: es el precio
 * de que no se mueva nunca por ninguna otra razón.
 */
export const CELDA_MAXIMA = { ancho: 38, fondo: 18 };

/** A qué múltiplo se redondea la celda hacia arriba. */
export const PASO = { ancho: 4, fondo: 3 };

/**
 * La celda que le hace falta a ESTA empresa.
 *
 * La primera versión usaba una celda constante —la mayor sala posible— y era
 * estable pero quedaba mal: con salas de 12 × 9 dentro de celdas de 38 × 18,
 * la planta se veía como chozas sueltas en un descampado y no como una
 * oficina. Se vio en el navegador el 01/11/2026 y no había forma de verlo
 * antes.
 *
 * Así que la celda sale de la sala más grande que la empresa tiene, redondeada
 * hacia arriba a un múltiplo: así un departamento que crece un poco no cambia
 * la celda, y la planta entera no se entera.
 *
 * LO QUE ESTO CUESTA, dicho sin suavizar: si un departamento crece lo
 * suficiente como para pasar el múltiplo, la celda crece y **todas las salas
 * se recolocan**. Agregar departamentos sigue sin mover a nadie —que era la
 * queja medida— pero agrandar mucho uno, sí. Es el precio de que la planta se
 * vea como una oficina, y está medido en la prueba.
 *
 * @param {any[]} salas
 */
export function celdaPara(salas) {
  const lista = (Array.isArray(salas) ? salas : []).filter(Boolean);
  const mayor = lista.reduce(
    (acc, s) => ({
      ancho: Math.max(acc.ancho, s?.planta?.mundo?.ancho ?? 0),
      fondo: Math.max(acc.fondo, s?.planta?.mundo?.fondo ?? 0)
    }),
    { ancho: 0, fondo: 0 }
  );
  //  UN pasillo y no dos. La primera version sumaba `AIRE * 2` -como si cada
  //  sala tuviera su propio pasillo a cada lado- y con salas de 14 x 10 daba
  //  celdas de 24 x 16: diez unidades de suelo pelado por sala, y la planta
  //  volvia a leerse como islas sueltas. El pasillo entre dos salas es UNO
  //  solo, y lo comparten.
  const arriba = (v, paso, minimo) =>
    Math.max(minimo, Math.ceil((v + AIRE) / paso) * paso);
  return {
    ancho: arriba(mayor.ancho, PASO.ancho, PASO.ancho * 2),
    fondo: arriba(mayor.fondo, PASO.fondo, PASO.fondo * 2)
  };
}

/** Lo que separa dos salas vecinas dentro de sus celdas. */
export const AIRE = 3;

/**
 * Las celdas que el patio se queda, y que ninguna sala puede ocupar.
 *
 * FIJAS, Y AHÍ ESTÁ TODA LA GRACIA. Un patio centrado de verdad tendría que
 * moverse cuando la rejilla crece, y mover el patio mueve todas las salas —que
 * es justo lo que este archivo existe para evitar—. Reservadas siempre, el
 * hueco está donde está desde el primer día y la sede crece a su alrededor.
 *
 * Son dos celdas y no una porque un patio cuadrado de una celda queda más
 * hondo que ancho: la celda es ancha y chata.
 *
 * Con pocos departamentos la rejilla ni siquiera llega hasta acá y no hay
 * patio, solo la plaza del frente. Es correcto: una empresa de tres
 * departamentos no tiene un patio interior.
 */
export const PATIO = [
  { columna: 1, fila: 1 },
  { columna: 2, fila: 1 }
];

const esPatio = (c) => PATIO.some((p) => p.columna === c.columna && p.fila === c.fila);

/**
 * La plaza: el vacío del frente, por donde se entra.
 *
 * No es decorado. Es lo que hace que la planta se lea como una sede y no como
 * un almacén de cubículos, y es donde va la recepción —que en la referencia
 * aprobada está justo ahí, al frente y al medio—.
 */
export const PLAZA = { fondo: 22, minimo: 12, parte: 0.3 };

/**
 * Cuánto fondo ocupa la plaza de una planta de este ancho.
 *
 * Proporcional y no fija: con un fondo constante de 22, una empresa de UN
 * departamento quedaba con una planta de 18 × 38 —esbeltez 0,47, más honda que
 * ancha— donde la entrada era el doble que la oficina. Un ISP chico tiene una
 * recepción chica.
 *
 * @param {number} ancho
 */
export function plazaPara(ancho) {
  return Number(Math.max(PLAZA.minimo, Math.min(PLAZA.fondo, ancho * PLAZA.parte)).toFixed(2));
}

/**
 * En qué celda va la sala número `i`, contando desde cero.
 *
 * CRECE EN L, Y HACIA DONDE HAGA FALTA PARA QUE LA PLANTA QUEDE CUADRADA.
 *
 * La primera versión completaba cuadrados de celdas —lado 1, lado 2, lado 3— y
 * eso daba una planta de esbeltez **2,05** para cualquier tamaño. El motivo es
 * que la celda no es cuadrada: mide 38 × 18 porque una sala es mucho más ancha
 * que profunda. Un cuadrado de celdas anchas es un rectángulo ancho, que es
 * justo la franja que el 31/10/2026 no se aprobó.
 *
 * Así que en cada paso se mira **el mundo, no la rejilla**: se agrega la
 * columna o la fila que deje la planta más cerca de ser cuadrada en unidades
 * reales. Sigue siendo una función pura de `i` —el crecimiento es siempre el
 * mismo, no depende de cuántas salas haya— y por eso sigue sin mover a nadie.
 *
 * @param {number} i
 * @returns {{columna: number, fila: number}}
 */
export function celdaDe(i, celda = CELDA_MAXIMA) {
  const n = Math.max(0, Math.trunc(i));
  return secuencia(n + 1, celda)[n];
}

/**
 * Las primeras `cuantas` celdas, en el orden en que se ocupan.
 *
 * Se recalcula entera y no se guarda en caché a propósito: es una secuencia de
 * decenas de elementos, y una caché que se invalide mal devolvería una planta
 * distinta para la misma empresa, que es el defecto que todo este archivo
 * existe para evitar.
 *
 * @param {number} cuantas
 */
function secuencia(cuantas, celda) {
  const celdas = [{ columna: 0, fila: 0 }];
  let columnas = 1;
  let filas = 1;
  while (celdas.length < cuantas) {
    //  Cuán lejos de cuadrada queda la planta si se crece por un lado o por el
    //  otro. Se compara en unidades del mundo, con la plaza incluida: la plaza
    //  ocupa fondo y sin contarla la planta saldría más ancha de la cuenta.
    const desvio = (c, f) => {
      const ancho = c * celda.ancho;
      const fondo = plazaPara(ancho) + f * celda.fondo;
      return Math.abs(ancho / fondo - 1);
    };
    //  Las celdas del patio se saltean, no se ocupan. Saltearlas no rompe la
    //  estabilidad: la reserva es la misma siempre, así que la sala número 7
    //  sigue cayendo en la misma celda tenga la empresa ocho departamentos o
    //  cuarenta.
    if (desvio(columnas + 1, filas) <= desvio(columnas, filas + 1)) {
      for (let f = 0; f < filas && celdas.length < cuantas; f++) {
        const c = { columna: columnas, fila: f };
        if (!esPatio(c)) celdas.push(c);
      }
      columnas++;
    } else {
      for (let c = 0; c < columnas && celdas.length < cuantas; c++) {
        const d = { columna: c, fila: filas };
        if (!esPatio(d)) celdas.push(d);
      }
      filas++;
    }
  }
  return celdas;
}

/**
 * Dónde cae una celda en el mundo.
 *
 * La plaza va delante de todo, así que las salas empiezan pasada su
 * profundidad. `gy` crece hacia el frente, igual que en el resto de la escena.
 *
 * @param {{columna: number, fila: number}} celda
 */
export function mundoDe(donde, celda = CELDA_MAXIMA) {
  return {
    x: donde.columna * celda.ancho,
    y: donde.fila * celda.fondo
  };
}

/**
 * La planta entera de una empresa: cada sala en su sitio, para siempre.
 *
 * El orden de entrada es el que manda y tiene que ser estable: se usa el que
 * trae `salas`, que sale de la configuración declarada. Reordenarlo acá —por
 * nombre, por tamaño, por piso— haría que renombrar un departamento lo mudara
 * de lugar.
 *
 * @param {any[]} salas las salas compuestas de la empresa
 * @returns {{
 *   puestas: {sala: any, x: number, y: number, ancho: number, fondo: number,
 *             columna: number, fila: number}[],
 *   huella: {ancho: number, fondo: number},
 *   plaza: {x: number, y: number, ancho: number, fondo: number}
 * }}
 */
export function repartirPlantaUnica(salas) {
  const lista = (Array.isArray(salas) ? salas : []).filter(Boolean);
  const celda = celdaPara(lista);
  if (lista.length === 0) {
    return {
      puestas: [],
      celda,
      patio: null,
      huella: { ancho: celda.ancho, fondo: plazaPara(celda.ancho) },
      plaza: { x: 0, y: 0, ancho: celda.ancho, fondo: plazaPara(celda.ancho) }
    };
  }

  //  La secuencia se calcula UNA vez para toda la empresa y no una por sala:
  //  `celdaDe(i)` la recalcula entera cada vez, y con cuarenta departamentos
  //  eso es cuarenta veces el mismo trabajo en cada fotograma.
  const celdas = secuencia(lista.length, celda);

  const puestas = lista.map((sala, i) => {
    const sitio = mundoDe(celdas[i], celda);
    const m = sala?.planta?.mundo ?? { ancho: 10, fondo: 8 };
    //  Centrada en su celda y no pegada a una esquina: una sala chica en la
    //  esquina de su celda deja todo el aire de un lado y se lee como si se
    //  hubiera caído. Centrada, el aire que le sobra es pasillo por los cuatro
    //  costados, que es lo que es.
    return {
      sala,
      x: Number((sitio.x + Math.max(AIRE, (celda.ancho - m.ancho) / 2)).toFixed(2)),
      y: Number((sitio.y + Math.max(AIRE, (celda.fondo - m.fondo) / 2)).toFixed(2)),
      ancho: m.ancho,
      fondo: m.fondo,
      columna: celdas[i].columna,
      fila: celdas[i].fila
    };
  });

  const columnas = Math.max(...puestas.map((p) => p.columna)) + 1;
  const filas = Math.max(...puestas.map((p) => p.fila)) + 1;
  const anchoTotal = columnas * celda.ancho;
  const fondoDeLaPlaza = plazaPara(anchoTotal);
  const huella = {
    ancho: anchoTotal,
    fondo: filas * celda.fondo + fondoDeLaPlaza
  };

  //  El patio, en coordenadas del mundo, SOLO si la rejilla llegó hasta sus
  //  celdas. Con pocos departamentos no existe, y devolver un rectángulo
  //  fuera del edificio dibujaría un suelo flotando al lado de la sede.
  const dentro = PATIO.filter((p) => p.columna < columnas && p.fila < filas);
  const patio = dentro.length === 0 ? null : {
    x: Math.min(...dentro.map((p) => p.columna)) * celda.ancho,
    y: Math.min(...dentro.map((p) => p.fila)) * celda.fondo,
    ancho: (Math.max(...dentro.map((p) => p.columna)) + 1
            - Math.min(...dentro.map((p) => p.columna))) * celda.ancho,
    fondo: (Math.max(...dentro.map((p) => p.fila)) + 1
            - Math.min(...dentro.map((p) => p.fila))) * celda.fondo
  };

  return {
    puestas,
    celda,
    patio,
    huella,
    //  LA PLAZA VA AL FRENTE, y el frente en esta proyección es el `gy` MAYOR.
    //
    //  La primera versión la puso en `gy = 0` creyendo que ahí estaba el
    //  frente, y en el navegador salió una losa pálida enorme al fondo, detrás
    //  de todo, que no se leía como una entrada sino como un muro. En esta
    //  isometría `gy` crece hacia quien mira: `edificio.js` lo dice sin
    //  decirlo, poniendo su circulación «al fondo» justo en `gy = 0`.
    plaza: {
      x: 0,
      y: filas * celda.fondo,
      ancho: huella.ancho,
      fondo: fondoDeLaPlaza
    }
  };
}
