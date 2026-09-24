/**
 * Geometria del mapa: donde va cada estacion y por donde pasa cada flujo.
 *
 * Existe ANTES que el mapa a proposito. La Fase 2 agrega los componentes que
 * la usan (FlowLine, el lienzo del mapa); esto es lo que hay que tener
 * resuelto y probado para que ese trabajo sea pintar, no calcular -- y es
 * justo donde el intento anterior fallo.
 *
 * LA LECCION QUE PAGA ESTE ARCHIVO (23/09/2026)
 * La primera version del centro de mando colocaba a los agentes en un anillo
 * con radios escritos a mano. Con seis se veia bien; con los ocho de Rapilink
 * las tarjetas se invadian, y cada ajuste de radio movia el problema a otro
 * punto. La causa no era el radio: era que CUANTOS AGENTES HAY LO DECIDE CADA
 * EMPRESA. Por eso aqui no hay ninguna constante de posicion: todo se deriva
 * de cuantos son y del alto que ocupa la tarjeta mas alta, que se mide, no se
 * estima.
 */

/**
 * Reparte n estaciones en un anillo eliptico.
 *
 * @param {number} n cuantas estaciones
 * @param {{ cx: number, cy: number, rx: number, ry: number, desde?: number }} caja
 * @returns {{ indice: number, x: number, y: number, angulo: number, mitadSuperior: boolean }[]}
 */
export function anillo(n, caja) {
  const { cx, cy, rx, ry, desde = -90 } = caja;
  if (n <= 0) return [];
  return Array.from({ length: n }, (_, i) => {
    const grados = desde + (360 / n) * i;
    const rad = (grados * Math.PI) / 180;
    const y = cy + ry * Math.sin(rad);
    return { indice: i, x: cx + rx * Math.cos(rad), y, angulo: grados, mitadSuperior: y < cy };
  });
}

/**
 * Los angulos de un anillo, repartidos por LONGITUD DE ARCO.
 *
 * `anillo` reparte en angulos iguales, que en una elipse achatada agolpa las
 * piezas donde la curva es mas cerrada -- medido el 24/09/2026 sobre el
 * prototipo: con ocho agentes, los cuatro de las diagonales se solapaban con
 * los laterales, 47x39 px cada uno. Repartir por arco deja a cada vecino a la
 * misma distancia REAL del siguiente, que es lo que decide si se tocan.
 *
 * Se resuelve muestreando la elipse (no hay forma cerrada para su perimetro);
 * 2000 pasos dan un error por debajo del pixel a cualquier radio razonable.
 *
 * @param {number} n cuantas piezas
 * @param {number} rx radio horizontal
 * @param {number} ry radio vertical
 * @param {number} [desde] angulo inicial en radianes (por omision, arriba)
 * @returns {number[]} angulos en radianes
 */
export function angulosPorArco(n, rx, ry, desde = -Math.PI / 2) {
  if (n <= 0) return [];
  const PASOS = 2000;
  const punto = (/** @type {number} */ t) => [rx * Math.cos(t), ry * Math.sin(t)];
  const acumulado = [0];
  let [ax, ay] = punto(desde);
  for (let k = 1; k <= PASOS; k++) {
    const [bx, by] = punto(desde + (2 * Math.PI * k) / PASOS);
    acumulado.push(acumulado[k - 1] + Math.hypot(bx - ax, by - ay));
    ax = bx;
    ay = by;
  }
  const total = acumulado[PASOS];
  return Array.from({ length: n }, (_, i) => {
    const objetivo = (total * i) / n;
    let k = acumulado.findIndex((v) => v >= objetivo);
    if (k < 0) k = PASOS;
    return desde + (2 * Math.PI * k) / PASOS;
  });
}

/**
 * Los radios del anillo mas grande que cabe, y si cabe alguno.
 *
 * Tres correcciones que costaron una pasada de medicion cada una:
 *
 * 1. El radio sale del espacio que HAY, no de un porcentaje del lienzo: con
 *    un porcentaje sobraban 80 px por lado en una ventana y faltaban en otra,
 *    porque cuanto mide una pieza depende de los nombres que cada empresa le
 *    ponga a sus agentes.
 * 2. Lo que se coloca sobre el anillo es el DISCO, no la caja: el nombre y la
 *    tarea cuelgan a un lado y desplazan el centro de la caja respecto al del
 *    disco. Colocando la caja, dos discos se metian 11 px dentro del nodo
 *    central (medido el 24/09/2026 a 1366x768). Ese corrimiento es `desfase`.
 * 3. Puede no caber ningun anillo. Antes eso se resolvia estirando el radio
 *    hasta el minimo y pintando igual -- con los discos encima del centro.
 *    Ahora se dice que no cabe y quien llama decide (hoy: rejilla).
 *
 * @param {{ ancho: number, alto: number, anchoPieza: number, altoPieza: number,
 *           desfase?: number, radioPieza?: number, radioCentro?: number,
 *           margen?: number, holguraCentro?: number }} medidas
 * @returns {{ rx: number, ry: number, cabe: boolean }}
 */
export function radiosDelAnillo({
  ancho,
  alto,
  anchoPieza,
  altoPieza,
  desfase = 0,
  radioPieza = 0,
  radioCentro = 0,
  margen = 16,
  holguraCentro = 12
}) {
  const rxMax = ancho / 2 - anchoPieza / 2 - margen;
  const ryMax = alto / 2 - altoPieza / 2 - margen - Math.abs(desfase);
  // El minimo lo marca la CAJA, no el disco: el nombre y la tarea son parte de
  // la pieza y quedan ilegibles encima del nodo central. Con el disco como
  // unica referencia, un lienzo de 439x500 daba "cabe" y el resultado real era
  // dos discos metidos 5 px en el centro y cinco piezas fuera (24/09/2026).
  const minimoX = Math.max(anchoPieza / 2, radioPieza) + radioCentro + holguraCentro;
  const minimoY = Math.max(altoPieza / 2, radioPieza) + radioCentro + holguraCentro;
  return {
    rx: Math.max(rxMax, minimoX),
    ry: Math.max(ryMax, minimoY),
    cabe: rxMax >= minimoX && ryMax >= minimoY
  };
}

/**
 * Si las piezas colocadas en esos angulos se pisan entre si.
 *
 * El radio dice si cabe el ANILLO; esto dice si caben las PIEZAS. Son cosas
 * distintas: con ocho agentes el anillo de 1045x599 va sobrado, y con once las
 * mismas piezas se montan unas sobre otras aunque el radio no haya cambiado.
 * Es el fallo que ya tuvo este mapa una vez -- se veia bien con seis y se
 * rompia con ocho -- y por eso se comprueba midiendo, no estimando cuantos
 * caben.
 *
 * @param {{ angulos: number[], rx: number, ry: number, anchoPieza: number,
 *           altoPieza: number, margen?: number }} disposicion
 */
export function seSolapanEnElAnillo({ angulos, rx, ry, anchoPieza, altoPieza, margen = 2 }) {
  const cajas = angulos.map((a) => ({
    x: rx * Math.cos(a) - anchoPieza / 2,
    y: ry * Math.sin(a) - altoPieza / 2,
    ancho: anchoPieza,
    alto: altoPieza
  }));
  for (let i = 0; i < cajas.length; i++) {
    for (let j = i + 1; j < cajas.length; j++) {
      if (seSolapan(cajas[i], cajas[j], margen)) return true;
    }
  }
  return false;
}

/**
 * Mete un punto hacia adentro para que la pieza centrada en el no se salga.
 * La ultima red: si el anillo no alcanza (lienzo angosto, nombre larguisimo),
 * la pieza se corre en vez de desbordar.
 *
 * @param {{ x: number, y: number }} punto centro deseado de la pieza
 * @param {{ ancho: number, alto: number }} pieza
 * @param {{ ancho: number, alto: number }} lienzo
 * @param {number} [margen]
 */
export function dentroDelLienzo(punto, pieza, lienzo, margen = 16) {
  const acotar = (/** @type {number} */ v, /** @type {number} */ medida, /** @type {number} */ limite) =>
    Math.min(Math.max(v, medida / 2 + margen), Math.max(medida / 2 + margen, limite - medida / 2 - margen));
  return {
    x: acotar(punto.x, pieza.ancho, lienzo.ancho),
    y: acotar(punto.y, pieza.alto, lienzo.alto)
  };
}

/**
 * El radio vertical maximo que cabe, dado el alto disponible y lo que ocupa
 * una tarjeta. Sin esto, la tarjeta de la estacion de arriba se sale del
 * lienzo -- pasó, y se arreglaba a ojo hasta que se midio: 165 px de alto
 * real contra 110 estimados.
 *
 * @param {{ alto: number, altoTarjeta: number, separacion?: number }} medidas
 */
export function radioVerticalMaximo({ alto, altoTarjeta, separacion = 80 }) {
  return Math.max(60, Math.floor((alto - 2 * (altoTarjeta + separacion)) / 2));
}

/**
 * Cuanto puede medir de ancho una estacion sin tocar a la vecina: el arco que
 * le toca sobre el anillo, con holgura.
 *
 * @param {{ n: number, rx: number, ry: number, holgura?: number, min?: number, max?: number }} medidas
 */
export function anchoDeEstacion({ n, rx, ry, holgura = 0.76, min = 170, max = 320 }) {
  if (n <= 0) return min;
  const perimetro = Math.PI * (rx + ry); // aproximacion suficiente para una elipse suave
  return Math.max(min, Math.min(max, (perimetro / n) * holgura));
}

/**
 * La curva de un flujo entre dos puntos. Sale y entra por el lado que mira al
 * otro, para que la linea no cruce por encima de la propia tarjeta.
 *
 * @param {{x: number, y: number}} desde
 * @param {{x: number, y: number}} hasta
 * @param {number} [curvatura] 0 = recta; 0.3 = curva suave
 */
export function rutaFlujo(desde, hasta, curvatura = 0.25) {
  const dx = hasta.x - desde.x;
  const dy = hasta.y - desde.y;
  if (curvatura === 0) return `M ${desde.x},${desde.y} L ${hasta.x},${hasta.y}`;
  // Control perpendicular al segmento: una curva que se aparta del centro.
  const mx = desde.x + dx / 2;
  const my = desde.y + dy / 2;
  const cx = mx - dy * curvatura;
  const cy = my + dx * curvatura;
  return `M ${desde.x},${desde.y} Q ${cx},${cy} ${hasta.x},${hasta.y}`;
}

/** Colores de flujo por lo que representa. Los usa FlowLine en la Fase 2. */
export const FLUJOS = {
  normal: '#2563EB',
  completado: '#22C55E',
  esperando: '#F59E0B',
  error: '#EF4444',
  escalamiento: '#8B5CF6'
};

/**
 * Dos cajas se pisan si se superponen en los dos ejes a la vez. Se usa para
 * comprobar una disposicion antes de pintarla -- medir el solape es lo que
 * convirtio "se ve mal" en un numero y permitio corregirlo.
 */
export function seSolapan(a, b, margen = 0) {
  const x = Math.min(a.x + a.ancho, b.x + b.ancho) - Math.max(a.x, b.x);
  const y = Math.min(a.y + a.alto, b.y + b.alto) - Math.max(a.y, b.y);
  return x > margen && y > margen;
}
