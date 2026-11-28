/**
 * LA PLANTA COMPACTA: varias filas de oficinas por piso.
 *
 * Esto es lo que el prototipo de PixiJS no podía tener, y conviene decir con
 * precisión por qué, porque la respuesta corta —«es el motor»— es falsa.
 *
 * EL PROBLEMA NO ES EL MOTOR, ES LA ESTRATEGIA DE OCLUSIÓN
 *
 * En `edificio.js` los tres niveles se dibujan SIEMPRE, ordenados por el
 * algoritmo del pintor. Con eso, la losa del nivel de arriba tapa el fondo del
 * de abajo, y la desigualdad que gobierna cuánto tapa —medida y escrita en ese
 * archivo— obliga a `H > z + (P − d)/0,8125`. Para dos filas de salas haría
 * falta `H > 28,7`: un edificio de 86 unidades de alto. De ahí sale la franja
 * larga, y de ahí sale que el 31/10/2026 el diseño no se aprobara.
 *
 * La salida no es dibujar mejor: es DEJAR DE DIBUJAR lo que estorba. Un piso
 * aislado no tiene nada encima, así que no hay nada que lo tape y la planta
 * puede ser todo lo profunda que quiera. En tres dimensiones reales eso es
 * gratis —se apaga una capa y el resto sigue siendo correcto, con su buffer de
 * profundidad—; en 2.5D ordenado por el pintor hay que recalcular el orden a
 * mano y cada excepción abre un agujero nuevo.
 *
 * Por eso este módulo NO importa Three.js: la distribución es una decisión de
 * geometría, no de dibujo, y tiene que poder probarse sin un lienzo. Si mañana
 * el motor elegido fuera otro, esto se queda.
 */

/** Separación entre dos salas de la misma fila, en celdas. */
export const SEPARACION = 2;
/** El pasillo entre dos filas de salas. Por ahí se circula. */
export const PASILLO = 5;
/** El núcleo vertical: escaleras y ascensor. Ocupa la esquina del edificio. */
export const NUCLEO = { ancho: 9, fondo: 9 };
/**
 * Lo que sube un piso sobre el anterior.
 *
 * En el prototipo de PixiJS son 15 unidades, y no por gusto: es el mínimo que
 * la desigualdad de oclusión permite para que la losa de arriba no tape los
 * escritorios de abajo. Acá son 7 —poco más que la altura de un muro— porque
 * la visibilidad se resuelve aislando el piso y no separándolos. Es la misma
 * diferencia, medida en unidades del mundo: 15 contra 7.
 */
export const ALTURA_DE_PISO = 7;
/** Lo que mide un muro de sala. */
export const ALTURA_DE_MURO = 4;

/**
 * Cuántas columnas usar para `n` salas.
 *
 * Se busca la planta más cuadrada posible, con un sesgo leve a lo ancho porque
 * una sala es más ancha que profunda (14×10 en la plantilla mayor): repartir
 * en columnas iguales daría una planta alargada en el otro sentido.
 *
 * @param {number} n
 */
export function columnasPara(n) {
  if (n <= 1) return Math.max(1, n);
  if (n <= 3) return 2;
  return Math.max(2, Math.round(Math.sqrt(n * 0.85)));
}

/**
 * Reparte las salas de un piso en una rejilla de filas y columnas.
 *
 * El ancho de una columna es el de su sala más ancha y el fondo de una fila el
 * de su sala más profunda: así los pasillos quedan rectos y alineados entre
 * filas. Una sala más chica que su columna deja aire a la derecha, que es lo
 * que hace un edificio real y no un rompecabezas.
 *
 * @param {any[]} salas
 * @returns {{ puestas: {sala: any, x: number, y: number, ancho: number, fondo: number,
 *             fila: number, columna: number}[], huella: {ancho: number, fondo: number} }}
 */
export function repartirPiso(salas) {
  const lista = Array.isArray(salas) ? salas.filter(Boolean) : [];
  if (lista.length === 0) {
    //  Un piso declarado y vacío sigue siendo un piso: tiene su núcleo y su
    //  losa. Devolver huella cero lo borraría del edificio, y un piso libre es
    //  un dato de la empresa, no un error.
    return { puestas: [], huella: { ancho: NUCLEO.ancho, fondo: NUCLEO.fondo } };
  }

  const columnas = columnasPara(lista.length);
  const filas = Math.ceil(lista.length / columnas);

  const medida = (s) => s?.planta?.mundo ?? { ancho: 10, fondo: 8 };

  //  Ancho de cada columna y fondo de cada fila.
  const anchoCol = new Array(columnas).fill(0);
  const fondoFila = new Array(filas).fill(0);
  lista.forEach((s, i) => {
    const f = Math.floor(i / columnas);
    const c = i % columnas;
    const m = medida(s);
    anchoCol[c] = Math.max(anchoCol[c], m.ancho);
    fondoFila[f] = Math.max(fondoFila[f], m.fondo);
  });

  //  Dónde empieza cada columna y cada fila.
  const xDe = [];
  let x = NUCLEO.ancho + SEPARACION;
  for (let c = 0; c < columnas; c++) {
    xDe.push(x);
    x += anchoCol[c] + SEPARACION;
  }
  const yDe = [];
  let y = 0;
  for (let f = 0; f < filas; f++) {
    yDe.push(y);
    y += fondoFila[f] + PASILLO;
  }

  const puestas = lista.map((sala, i) => {
    const f = Math.floor(i / columnas);
    const c = i % columnas;
    const m = medida(sala);
    return { sala, x: xDe[c], y: yDe[f], ancho: m.ancho, fondo: m.fondo, fila: f, columna: c };
  });

  return {
    puestas,
    huella: {
      ancho: x - SEPARACION,
      fondo: Math.max(NUCLEO.fondo, y - PASILLO)
    }
  };
}

/**
 * El edificio compacto completo, nivel por nivel.
 *
 * La huella del edificio es la del piso más grande, y TODOS los pisos la
 * comparten. Es lo contrario de lo que hace `edificio.js`, donde cada nivel
 * mide lo suyo y el escalonado es información verdadera: acá el edificio tiene
 * un volumen único y un piso con menos salas tiene más espacio libre, que es
 * igual de verdadero y se parece más a la referencia aprobada.
 *
 * @param {any[]} pisos los niveles, como los devuelve `pisosDe`
 * @param {{ soloNivel?: number|null }} [opciones]
 */
export function edificioCompacto(pisos, opciones = {}) {
  const niveles = Array.isArray(pisos) ? pisos : [];
  const soloNivel = opciones.soloNivel ?? null;
  if (niveles.length === 0) {
    return { niveles: [], huella: { ancho: 0, fondo: 0 }, alto: 0 };
  }

  const nivelMinimo = Math.min(...niveles.map((p) => p.nivel));
  const repartos = niveles.map((piso) => ({ piso, ...repartirPiso(piso.salas ?? []) }));

  const huella = repartos.reduce(
    (acc, r) => ({
      ancho: Math.max(acc.ancho, r.huella.ancho),
      fondo: Math.max(acc.fondo, r.huella.fondo)
    }),
    { ancho: 0, fondo: 0 }
  );

  const salida = repartos
    .filter((r) => soloNivel === null || r.piso.nivel === soloNivel)
    .map((r) => ({
      nivel: r.piso.nivel,
      rotulo: String(r.piso.rotulo ?? ''),
      declarado: r.piso.declarado !== false,
      //  Aislado, el piso baja al suelo: mirar un nivel solo, flotando a dos
      //  pisos de altura, no dice nada y deja la cámara encuadrando vacío.
      gz: soloNivel !== null ? 0 : (r.piso.nivel - nivelMinimo) * ALTURA_DE_PISO,
      salas: r.puestas
    }));

  return {
    niveles: salida,
    huella,
    alto: salida.reduce((m, n) => Math.max(m, n.gz), 0) + ALTURA_DE_PISO
  };
}
