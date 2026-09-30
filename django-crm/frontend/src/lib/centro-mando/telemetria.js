/**
 * Las cuentas de los instrumentos de cada tarjeta.
 *
 * Vive aparte del dibujo porque es aritmetica con trampas: una serie toda en
 * cero no puede dividirse por su maximo, una carga sin referencia no dice
 * nada, y un pico aislado no debe aplastar el resto de la linea. Todo eso se
 * prueba sin montar un SVG.
 */

/** Cuantos cubos trae la serie que manda el motor: 15 de 2 minutos. */
export const CUBOS = 15;
export const MINUTOS_POR_CUBO = 2;

/**
 * Lleva la serie a alturas de 0 a 1 contra su propio maximo.
 *
 * Contra SU maximo y no contra el de todos los agentes: lo que interesa de
 * esta linea es la forma -- si el agente viene subiendo, cayendo o a tirones --
 * no comparar su volumen con el del vecino. Para comparar volumen esta el
 * anillo, que si usa una referencia comun.
 *
 * @param {number[]} serie
 * @returns {number[]} misma longitud, valores 0..1
 */
export function normalizarSerie(serie) {
  const datos = Array.isArray(serie) ? serie : [];
  const relleno = Array.from({ length: CUBOS }, (_, i) => Number(datos[i]) || 0);
  const techo = Math.max(...relleno);
  // Sin actividad la linea es plana abajo, no una division por cero.
  if (techo <= 0) return relleno.map(() => 0);
  return relleno.map((v) => v / techo);
}

/** ¿Hubo algo en la ventana? Decide si se dibuja la linea o el aviso de vacio. */
export const hayActividad = (serie) => normalizarSerie(serie).some((v) => v > 0);

/**
 * La ruta SVG de la serie, en una caja de ancho x alto.
 * Se dibuja de izquierda (hace 30 min) a derecha (ahora).
 */
export function rutaSparkline(serie, ancho, alto) {
  const v = normalizarSerie(serie);
  const paso = v.length > 1 ? ancho / (v.length - 1) : ancho;
  return v
    .map((n, i) => `${i === 0 ? 'M' : 'L'} ${(i * paso).toFixed(1)},${(alto - n * alto).toFixed(1)}`)
    .join(' ');
}

/** La misma serie como area cerrada, para el relleno bajo la linea. */
export function rutaArea(serie, ancho, alto) {
  return `${rutaSparkline(serie, ancho, alto)} L ${ancho},${alto} L 0,${alto} Z`;
}

/**
 * Cuanto se llena el anillo de un agente.
 *
 * La referencia es el agente MAS cargado de la pantalla, no un tope
 * inventado: "16 conversaciones" no significa nada suelto, y significa todo
 * si el que mas tiene lleva 31. Con todos en cero, nadie se llena.
 *
 * @param {number} valor
 * @param {number} referencia el maximo entre los agentes
 * @returns {number} 0..1
 */
export function proporcionCarga(valor, referencia) {
  const v = Number(valor) || 0;
  const r = Number(referencia) || 0;
  if (r <= 0 || v <= 0) return 0;
  return Math.min(1, v / r);
}

/** El maximo de conversaciones entre los agentes. Es la referencia del anillo. */
export const cargaMaxima = (agentes) =>
  (agentes || []).reduce((m, a) => Math.max(m, Number(a?.conversaciones) || 0), 0);

/**
 * El arco del anillo, en atributos de un circle con stroke-dasharray.
 * Se devuelve el par (pintado, resto) para no repetir la cuenta en el markup.
 */
export function arcoAnillo(proporcion, radio) {
  const vuelta = 2 * Math.PI * radio;
  const pintado = Math.max(0, Math.min(1, proporcion)) * vuelta;
  return { pintado, resto: vuelta - pintado, vuelta };
}
