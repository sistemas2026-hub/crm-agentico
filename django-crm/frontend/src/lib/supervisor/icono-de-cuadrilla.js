/**
 * LA MOTO CON TRÁILER DEL MAPA (02/11/2026).
 *
 * El usuario: «para qué punto sea como un carrito o una moto con tráiler,
 * algo pequeño en 3D».
 *
 * NO ES 3D DE VERDAD, Y ES A PROPÓSITO. Un modelo 3D sobre un mapa obliga a
 * cambiar Leaflet por un motor de tiles vectoriales, que pide proveedor y
 * clave, y a cargar una librería de gráficos entera. Días de trabajo y una
 * página mucho más pesada, para que el supervisor vea mejor un punto.
 *
 * Esto es **2.5D**: un dibujo en perspectiva, con sombra en el piso y dos
 * tonos por superficie. Da el volumen, pesa unos cientos de bytes, es nítido
 * en cualquier zoom —es SVG, no una imagen— y se puede teñir.
 *
 * EL COLOR SIGUE SIGNIFICANDO LO MISMO que cuando era un círculo: lleno =
 * reportó hace poco; apagado = es dónde estuvo, no dónde está. Que el dibujo
 * sea más lindo no puede hacerle perder al supervisor el dato de si lo que ve
 * es de ahora.
 */

/** Alto y ancho del dibujo, en píxeles de pantalla. */
export const TAMANO = { ancho: 46, alto: 34 };

/**
 * El SVG de la moto con tráiler, teñida.
 *
 * @param {string} color el del cuerpo; el tráiler va un tono por debajo
 * @param {boolean} fresca atenúa todo cuando la posición ya no es de ahora
 */
export function motoConTrailer(color, fresca) {
  const o = fresca ? 1 : 0.5;
  return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 46 34" width="46" height="34"
     aria-hidden="true" style="opacity:${o}">
  <ellipse cx="23" cy="30" rx="17" ry="3.4" fill="#000" opacity="0.22"/>
  <g>
    <path d="M3 22 L12 17 L22 20 L13 25 Z" fill="${color}" opacity="0.55"/>
    <path d="M3 22 L13 25 L13 28 L3 25 Z" fill="${color}" opacity="0.32"/>
    <path d="M13 25 L22 20 L22 23 L13 28 Z" fill="${color}" opacity="0.42"/>
    <rect x="11" y="20" width="9" height="2" rx="1" fill="#1c2430" opacity="0.5"/>
    <path d="M20 19 L26 16 L29 17 L23 20 Z" fill="#59636f"/>
    <path d="M24 17 L33 12 L41 15 L32 20 Z" fill="${color}"/>
    <path d="M24 17 L32 20 L32 24 L24 21 Z" fill="${color}" opacity="0.6"/>
    <path d="M32 20 L41 15 L41 19 L32 24 Z" fill="${color}" opacity="0.78"/>
    <path d="M36 13 L40 10 L43 11 L39 14 Z" fill="#2b3440"/>
    <circle cx="12" cy="25" r="4.2" fill="#161c24"/>
    <circle cx="12" cy="25" r="1.7" fill="#5b6672"/>
    <circle cx="34" cy="22" r="5" fill="#161c24"/>
    <circle cx="34" cy="22" r="2" fill="#5b6672"/>
    <path d="M33 12 L41 15 L41 16.4 L33 13.4 Z" fill="#fff" opacity="0.28"/>
  </g>
</svg>`.trim();
}

/**
 * Lo que Leaflet necesita para dibujarla: el HTML del marcador y dónde cae el
 * punto exacto. El ancla va en la **rueda de atrás**, no en el centro del
 * dibujo: el punto es dónde está la cuadrilla, y si se ancla al medio el
 * vehículo queda corrido respecto de la calle.
 *
 * @param {string} color
 * @param {boolean} fresca
 */
export function opcionesDelIcono(color, fresca) {
  return {
    html: motoConTrailer(color, fresca),
    className: 'mp-vehiculo',
    iconSize: [TAMANO.ancho, TAMANO.alto],
    iconAnchor: [12, 29]
  };
}
