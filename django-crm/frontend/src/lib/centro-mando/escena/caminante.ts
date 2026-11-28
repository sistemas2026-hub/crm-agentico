import { Container, Graphics } from 'pixi.js';
import { PALETA, tono } from './paleta';

/**
 * UNA FIGURA DE PIE QUE CAMINA.
 *
 * `personaje.ts` dibuja a alguien SENTADO: su silla, sus piernas dobladas bajo
 * el escritorio y una pose que interpola entre cinco estados de trabajo. No
 * sirve para esto y no hay que forzarlo — un personaje sentado al que se le
 * estiran las piernas se ve exactamente como lo que es.
 *
 * Esta figura es mucho más simple a propósito, y el motivo no es la prisa: se
 * ve de lejos, cruzando un patio, a escala de edificio. Un cuerpo, una cabeza,
 * dos piernas que alternan y un balanceo. Todo lo que se le agregue encima no
 * se va a ver y sí se va a pagar en cada fotograma.
 *
 * LO QUE ESTA FIGURA NO TIENE, Y ES DELIBERADO: nombre, placa, sombra de
 * selección y cualquier otra cosa que la haga parecer un puesto. Una figura de
 * ambiente que se pudiera pulsar sería un empleado inventado con ficha.
 */

/** El color de cada oficio. Son etiquetas de dibujo, no roles de la empresa. */
const ROPA: Record<string, { cuerpo: number; detalle: number }> = {
  aseo: { cuerpo: 0x3f9e7a, detalle: 0x2b7a5c },
  bodega: { cuerpo: 0xb4802f, detalle: 0x8a5f1f },
  visita: { cuerpo: 0x6b7280, detalle: 0x4b5563 }
};

export interface Caminante {
  nodo: Container;
  /** Aplica el balanceo del paso. `fase` crece con el tiempo; `andando` lo apaga. */
  paso(fase: number, andando: boolean): void;
  destruir(): void;
}

/**
 * @param oficio cuál de los colores lleva
 */
export function construirCaminante(oficio: string): Caminante {
  const nodo = new Container();
  const ropa = ROPA[oficio] ?? ROPA.visita;

  //  La sombra en el suelo. Es lo que ancla la figura al piso: sin ella
  //  parece flotando, y en isometría eso se nota más que en cualquier otra
  //  proyección porque no hay horizonte contra el que juzgar la altura.
  const sombra = new Graphics();
  sombra.ellipse(0, 0, 6.5, 3).fill({ color: 0x05040f, alpha: 0.34 });
  nodo.addChild(sombra);

  const piernaIzq = new Graphics();
  const piernaDer = new Graphics();
  for (const [g, color] of [[piernaIzq, ropa.detalle], [piernaDer, tono(ropa.detalle, -0.12)]] as const) {
    g.roundRect(-2.2, -14, 4.4, 15, 1.6).fill({ color });
  }
  nodo.addChild(piernaDer);
  nodo.addChild(piernaIzq);

  //  El tronco: más estrecho en la cadera que en los hombros, igual que en el
  //  personaje sentado. Un rectángulo recto se lee como una caja con cabeza.
  const cuerpo = new Container();
  const tronco = new Graphics();
  tronco
    .poly([-5.4, -14, 5.4, -14, 6.6, -29, -6.6, -29])
    .fill({ color: ropa.cuerpo })
    .poly([-6.6, -29, 6.6, -29, 5.6, -31.5, -5.6, -31.5])
    .fill({ color: tono(ropa.cuerpo, 0.16) });
  const brazos = new Graphics();
  brazos
    .roundRect(-8.2, -28, 3.2, 13, 1.5).fill({ color: tono(ropa.cuerpo, -0.14) })
    .roundRect(5.0, -28, 3.2, 13, 1.5).fill({ color: tono(ropa.cuerpo, -0.14) });
  const cabeza = new Graphics();
  cabeza
    .ellipse(0, -36.5, 5.2, 5.8).fill({ color: PALETA.piel })
    .poly([-5.2, -39.5, 5.2, -39.5, 4.2, -42.6, -4.2, -42.6])
    .fill({ color: PALETA.pelo });
  cuerpo.addChild(brazos);
  cuerpo.addChild(tronco);
  cuerpo.addChild(cabeza);
  nodo.addChild(cuerpo);

  return {
    nodo,
    paso(fase: number, andando: boolean) {
      //  Quieta tambien respira: una figura detenida del todo se lee como una
      //  calcomania pegada al suelo. Es el mismo criterio que el reposo del
      //  personaje sentado.
      if (!andando) {
        const r = Math.sin(fase * 1.6) * 0.5;
        piernaIzq.y = 0;
        piernaDer.y = 0;
        piernaIzq.x = -2.6;
        piernaDer.x = 2.6;
        cuerpo.y = r;
        return;
      }
      const s = Math.sin(fase * 7.5);
      piernaIzq.x = -1.2 + s * 2.6;
      piernaDer.x = 1.2 - s * 2.6;
      piernaIzq.y = -Math.max(0, s) * 2.2;
      piernaDer.y = -Math.max(0, -s) * 2.2;
      //  El cuerpo sube en cada apoyo: es lo que convierte dos piernas que se
      //  abren y cierran en alguien caminando.
      cuerpo.y = -Math.abs(s) * 1.1;
      brazos.rotation = s * 0.08;
    },
    destruir() {
      nodo.destroy({ children: true });
    }
  };
}
