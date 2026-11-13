/**
 * LOS PRIMITIVOS DE VOLUMEN: una caja, un panel de muro, y nada más.
 *
 * Vivían dentro de `oficina.ts`. Salieron de ahí el 31/10/2026, cuando la
 * reconstrucción arquitectónica necesitó dibujar cajas y paneles desde un
 * segundo archivo.
 *
 * LA RAZÓN DE QUE NO SE COPIARAN ES EL SIGNO DE LA LUZ.
 * Los dos cantos de una caja se derivan de la tapa —−18% el de la derecha,
 * −34% el de la izquierda— y el día que esas constantes existan en dos sitios,
 * un archivo quedará con la luz entrando por el otro lado. Una fachada
 * iluminada al revés no da error, no rompe ninguna prueba y se ve a la primera
 * en una captura, que es el peor sitio donde descubrirlo.
 *
 * Nada de acá sabe qué es una sala, un edificio o una empresa: recibe celdas y
 * un color.
 */

import { Graphics } from 'pixi.js';
import { aPantalla } from './isometria';
import { tono } from './paleta';

/** Una lista de puntos → el array plano que quiere `Graphics.poly`. */
export function aplanar(puntos: { x: number; y: number }[]): number[] {
  const salida: number[] = [];
  for (const p of puntos) salida.push(p.x, p.y);
  return salida;
}

/**
 * Una caja isométrica con sus tres caras visibles.
 *
 * Es la pieza con la que está hecho el 80% del mobiliario. Los dos cantos se
 * derivan de la tapa (−18% y −34%): declararlos a mano para cada mueble es cómo
 * termina habiendo un escritorio iluminado desde la izquierda en una sala
 * iluminada desde la derecha.
 */
export function caja(
  g: Graphics,
  gx: number,
  gy: number,
  gz: number,
  ancho: number,
  fondo: number,
  alto: number,
  color: number,
  alpha = 1
) {
  const z = gz + alto;
  const t = [
    aPantalla(gx, gy + fondo, z),
    aPantalla(gx, gy, z),
    aPantalla(gx + ancho, gy, z),
    aPantalla(gx + ancho, gy + fondo, z)
  ];
  // Canto que mira hacia el espectador por la derecha (+gx).
  const d = [
    aPantalla(gx + ancho, gy, z),
    aPantalla(gx + ancho, gy + fondo, z),
    aPantalla(gx + ancho, gy + fondo, gz),
    aPantalla(gx + ancho, gy, gz)
  ];
  // Canto que mira hacia el espectador por la izquierda (+gy).
  const i = [
    aPantalla(gx, gy + fondo, z),
    aPantalla(gx + ancho, gy + fondo, z),
    aPantalla(gx + ancho, gy + fondo, gz),
    aPantalla(gx, gy + fondo, gz)
  ];
  g.poly(aplanar(i)).fill({ color: tono(color, -0.34), alpha });
  g.poly(aplanar(d)).fill({ color: tono(color, -0.18), alpha });
  g.poly(aplanar(t)).fill({ color, alpha });
}

/**
 * Un panel plano pegado al muro de `gy = 0`, visto de frente.
 *
 * Las coordenadas son (gx, altura) porque un panel de pared no tiene fondo. Hay
 * una función por muro y no una genérica con un parámetro de orientación: la
 * versión genérica es la que termina con un panel espejado, y un texto espejado
 * dentro de una pared oscura no se ve en una captura.
 */
export function panelMuroFondo(
  g: Graphics,
  gx: number,
  ancho: number,
  z0: number,
  z1: number,
  color: number,
  alpha = 1
) {
  const p = [
    aPantalla(gx, 0, z1),
    aPantalla(gx + ancho, 0, z1),
    aPantalla(gx + ancho, 0, z0),
    aPantalla(gx, 0, z0)
  ];
  g.poly(aplanar(p)).fill({ color, alpha });
}

/** Lo mismo, en el muro de `gx = 0`. */
export function panelMuroLateral(
  g: Graphics,
  gy: number,
  ancho: number,
  z0: number,
  z1: number,
  color: number,
  alpha = 1
) {
  const p = [
    aPantalla(0, gy, z1),
    aPantalla(0, gy + ancho, z1),
    aPantalla(0, gy + ancho, z0),
    aPantalla(0, gy, z0)
  ];
  g.poly(aplanar(p)).fill({ color, alpha });
}

/**
 * Un panel vertical en un plano `gx = constante`, mirando al espectador.
 *
 * Es la cara de un extremo del edificio: la que cierra la sección. No es
 * `panelMuroLateral` desplazado — ese vive pegado a `gx = 0` y no acepta otra
 * columna, que es justo lo que hace falta para el extremo opuesto.
 */
export function panelEnX(
  g: Graphics,
  gx: number,
  gy: number,
  fondo: number,
  z0: number,
  z1: number,
  color: number,
  alpha = 1
) {
  const p = [
    aPantalla(gx, gy, z1),
    aPantalla(gx, gy + fondo, z1),
    aPantalla(gx, gy + fondo, z0),
    aPantalla(gx, gy, z0)
  ];
  g.poly(aplanar(p)).fill({ color, alpha });
}

/**
 * Un panel vertical en un plano `gy = constante`.
 *
 * El gemelo del anterior para el otro eje: el frente de la sección, el
 * antepecho de una terraza, el peto de una cubierta.
 */
export function panelEnY(
  g: Graphics,
  gy: number,
  gx: number,
  ancho: number,
  z0: number,
  z1: number,
  color: number,
  alpha = 1
) {
  const p = [
    aPantalla(gx, gy, z1),
    aPantalla(gx + ancho, gy, z1),
    aPantalla(gx + ancho, gy, z0),
    aPantalla(gx, gy, z0)
  ];
  g.poly(aplanar(p)).fill({ color, alpha });
}

/** Un plano horizontal a altura `gz`: una losa, una cubierta, una terraza. */
export function losaPlana(
  g: Graphics,
  gx: number,
  gy: number,
  ancho: number,
  fondo: number,
  gz: number,
  color: number,
  alpha = 1
) {
  const p = [
    aPantalla(gx, gy + fondo, gz),
    aPantalla(gx, gy, gz),
    aPantalla(gx + ancho, gy, gz),
    aPantalla(gx + ancho, gy + fondo, gz)
  ];
  g.poly(aplanar(p)).fill({ color, alpha });
}
