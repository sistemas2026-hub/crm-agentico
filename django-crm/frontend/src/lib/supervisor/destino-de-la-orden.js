/**
 * QUÉ SE PUEDE DIBUJAR DE CADA CUADRILLA (05/11/2026).
 *
 * El usuario empezó a cargarle coordenadas a sus clientes y no las veía: la
 * orden las guardaba desde siempre y no llegaban a ninguna pantalla.
 *
 * LOS CUATRO ESCENARIOS, que son del pedido del usuario (punto 6 de su spec)
 * y no de un caso de borde inventado:
 *
 *   A  el técnico reporta y la orden NO tiene coordenadas
 *      -> se dibuja el vehículo; la orden se marca «sin ubicación»; NO se
 *         inventa el punto del cliente ni se traza una ruta hacia él.
 *   B  el técnico NO reporta y la orden SÍ tiene
 *      -> se dibuja el destino; se dice que no hay ubicación del técnico.
 *   C  ninguno de los dos
 *      -> la cuadrilla sigue en la lista, sin marcador ninguno.
 *   D  los dos
 *      -> se dibujan ambos, distintos, y se los une con una línea.
 *
 * LA REGLA QUE ATRAVIESA LOS CUATRO: **no se inventa un punto**. Ni se
 * geocodifica la dirección, ni se usa el centro del barrio, ni se deja la
 * última posición conocida haciéndose pasar por la de ahora. Un punto en un
 * mapa se lee como un hecho, y mandar a alguien a una coordenada adivinada
 * es peor que no mostrarle ninguna.
 *
 * Vive acá y no dentro del componente porque una condición escrita en la
 * plantilla no la mira ninguna prueba; ya pasó con la regla de qué día se
 * dibuja el mapa.
 */

/**
 * @typedef {Object} QueDibujar
 * @property {'A'|'B'|'C'|'D'} escenario
 * @property {{latitud:number, longitud:number}|null} vehiculo dónde está la cuadrilla
 * @property {{latitud:number, longitud:number}|null} destino  dónde queda el cliente
 * @property {boolean} une  si se traza la línea entre los dos
 * @property {string} falta lo que hay que decir en palabras, o ''
 */

/** La orden que manda en el mapa: la que la cuadrilla hace ahora, o la que sigue. */
export function ordenDelFoco(cuadrilla) {
  const ordenes = cuadrilla?.ordenes ?? [];
  return ordenes.find((/** @type {any} */ o) => o.siguiente) ?? ordenes[0] ?? null;
}

/**
 * Qué dibujar de una cuadrilla. Ver el encabezado.
 *
 * @param {any} cuadrilla como la devuelve `campo/dia_publicado.py`
 * @returns {QueDibujar}
 */
export function queDibujar(cuadrilla) {
  const p = cuadrilla?.posicion ?? null;
  const foco = ordenDelFoco(cuadrilla);
  const d = foco?.destino ?? null;

  const vehiculo = p ? { latitud: p.latitud, longitud: p.longitud } : null;
  const destino = d && d.latitud != null && d.longitud != null
    ? { latitud: d.latitud, longitud: d.longitud }
    : null;

  if (vehiculo && destino) {
    return { escenario: 'D', vehiculo, destino, une: true, falta: '' };
  }
  if (vehiculo && !destino) {
    return {
      escenario: 'A',
      vehiculo,
      destino: null,
      une: false,
      falta: foco
        ? `OT #${foco.numero} sin ubicación: abrila y corregila.`
        : 'Sin orden en curso.'
    };
  }
  if (!vehiculo && destino) {
    return {
      escenario: 'B',
      vehiculo: null,
      destino,
      une: false,
      falta: 'Sin ubicación del técnico: solo se ve a dónde va.'
    };
  }
  return {
    escenario: 'C',
    vehiculo: null,
    destino: null,
    une: false,
    falta: foco
      ? `Sin ubicación del técnico y la OT #${foco.numero} no tiene coordenadas.`
      : 'Sin ubicación del técnico.'
  };
}

/** El pin del destino: una casa, para que no se confunda con el vehículo. */
export function destinoSvg() {
  return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 34" width="26" height="34"
     aria-hidden="true">
  <ellipse cx="13" cy="31" rx="7" ry="2.2" fill="#000" opacity="0.22"/>
  <path d="M13 1 C6.4 1 1.6 6 1.6 12 C1.6 20 13 30 13 30 S24.4 20 24.4 12
           C24.4 6 19.6 1 13 1 Z" fill="#8a5300"/>
  <path d="M13 1 C6.4 1 1.6 6 1.6 12 C1.6 14 2.4 16 3.6 18 C3 15 3.4 8 13 6 Z"
        fill="#fff" opacity="0.2"/>
  <path d="M7.6 13 L13 8.4 L18.4 13 L18.4 18.6 L7.6 18.6 Z" fill="#fff"/>
  <rect x="11.2" y="14.6" width="3.6" height="4" fill="#8a5300"/>
</svg>`.trim();
}

/** Lo que Leaflet necesita: el pin se ancla en su punta. */
export function opcionesDelDestino() {
  return {
    html: destinoSvg(),
    className: 'mp-destino',
    iconSize: [26, 34],
    iconAnchor: [13, 30]
  };
}
