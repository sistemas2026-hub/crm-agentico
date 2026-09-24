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
