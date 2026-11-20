/**
 * EL TÉCNICO EN EL MAPA (02/11/2026; rehecho el 05/11/2026).
 *
 * Primero fue una moto con tráiler. El usuario, al verla sobre el satélite:
 * «el ícono del técnico no se distingue bien, dale más creatividad, mejor
 * haz una persona en 3D». Tenía razón por un motivo concreto: un vehículo
 * chico y verde sobre un techo gris o sobre vegetación se pierde, y una
 * silueta de persona se reconoce de un vistazo aunque sea pequeña.
 *
 * NO ES 3D DE VERDAD, Y ES A PROPÓSITO. Un modelo 3D sobre un mapa obliga a
 * cambiar Leaflet por un motor de tiles vectoriales, que pide proveedor y
 * clave, y a cargar una librería de gráficos entera. Días de trabajo y una
 * página mucho más pesada, para que el supervisor vea mejor un punto.
 *
 * Esto es **2.5D**: perspectiva, sombra en el piso y dos tonos por
 * superficie. Da el volumen, pesa unos cientos de bytes y es nítido en
 * cualquier zoom, porque es SVG y no una imagen.
 *
 * LO QUE LO HACE VISIBLE, que es el punto del cambio:
 *   - un **halo blanco** alrededor de toda la figura, para que recorte
 *     contra el satélite igual que contra el mapa claro;
 *   - un **casco amarillo**, que no aparece en una foto aérea de un barrio;
 *   - más alto que ancho: una silueta vertical se separa del fondo.
 *
 * EL COLOR DEL CHALECO SIGUE SIGNIFICANDO LO MISMO que cuando era un
 * círculo: lleno = reportó hace poco; apagado = es dónde estuvo, no dónde
 * está. Que el dibujo sea más lindo no puede hacerle perder al supervisor el
 * dato de si lo que ve es de ahora.
 */

/** Alto y ancho del dibujo, en píxeles de pantalla. */
export const TAMANO = { ancho: 34, alto: 46 };

/**
 * El SVG del técnico, teñido.
 *
 * @param {string} color el del chaleco
 * @param {boolean} fresca atenúa todo cuando la posición ya no es de ahora
 */
export function tecnicoDePie(color, fresca) {
  const o = fresca ? 1 : 0.5;
  return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 34 46" width="34" height="46"
     aria-hidden="true" style="opacity:${o}">
  <ellipse cx="17" cy="42" rx="9" ry="3" fill="#000" opacity="0.28"/>
  <g stroke="#fff" stroke-width="2.6" stroke-linejoin="round" fill="none">
    <path d="M13 40 L13 29 L21 29 L21 40"/>
    <path d="M10 18 L24 18 L23 30 L11 30 Z"/>
    <circle cx="17" cy="11" r="5"/>
    <path d="M8 10 L26 10 L24.5 7.5 C23 4 20.5 2.5 17 2.5 S11 4 9.5 7.5 Z"/>
  </g>
  <g>
    <path d="M13 40 L13 29 L16.4 29 L16.4 40 Z" fill="#2b3440"/>
    <path d="M17.6 40 L17.6 29 L21 29 L21 40 Z" fill="#222b36"/>
    <circle cx="17" cy="11.5" r="4.6" fill="#c68b5e"/>
    <path d="M17 6.9 A4.6 4.6 0 0 1 17 16.1 Z" fill="#a8734a"/>
    <path d="M10 18 L24 18 L23 30 L11 30 Z" fill="${color}"/>
    <path d="M17 18 L24 18 L23 30 L17 30 Z" fill="${color}" opacity="0.72"/>
    <path d="M11.6 21.4 L22.4 21.4 L22.3 23 L11.7 23 Z" fill="#fff" opacity="0.85"/>
    <path d="M15.6 18 L18.4 18 L18.4 30 L15.6 30 Z" fill="#fff" opacity="0.55"/>
    <path d="M8 10 L26 10 L24.5 7.5 C23 4 20.5 2.5 17 2.5 S11 4 9.5 7.5 Z" fill="#f2b705"/>
    <path d="M17 2.5 C20.5 2.5 23 4 24.5 7.5 L26 10 L17 10 Z" fill="#d49a04"/>
    <rect x="8" y="9.4" width="18" height="2.1" rx="1" fill="#ffd34d"/>
  </g>
</svg>`.trim();
}

/**
 * Lo que Leaflet necesita para dibujarlo: el HTML del marcador y dónde cae el
 * punto exacto. El ancla va en los **pies**, no en el centro del dibujo: el
 * punto es dónde está la cuadrilla, y anclado al medio la figura queda
 * flotando media cuadra más arriba de donde está.
 *
 * @param {string} color
 * @param {boolean} fresca
 */
export function opcionesDelIcono(color, fresca) {
  return {
    html: tecnicoDePie(color, fresca),
    className: 'mp-vehiculo',
    iconSize: [TAMANO.ancho, TAMANO.alto],
    iconAnchor: [17, 42]
  };
}
