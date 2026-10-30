/**
 * LA CÁMARA: zoom, desplazamiento y —lo que más cuesta— distinguir un clic de
 * un arrastre.
 *
 * No importa PixiJS. Mantiene tres números (x, y, escala) y responde qué
 * transformación aplicar; quien monta la escena se la pasa al contenedor. Así
 * la cámara se prueba en Node, y el motor gráfico se puede cambiar sin tocar
 * este archivo.
 *
 * EL DEFECTO QUE ESTE ARCHIVO EXISTE PARA NO REPETIR
 * En el plano anterior, `setPointerCapture` se robaba el clic: al pulsar un
 * puesto el navegador entregaba el puntero al contenedor del arrastre y el
 * `click` nunca llegaba al puesto. Se descubrió a mano, con el navegador,
 * porque no hay pruebas de interacción en este repositorio.
 *
 * La causa de fondo no era la captura del puntero: era que **nadie había
 * decidido qué separa un clic de un arrastre**. Acá sí está decidido, es un
 * número, y se puede probar: `gesto()` recibe los dos puntos y el tiempo, y
 * dice `clic` o `arrastre`. La escena no vuelve a adivinarlo.
 */

/** Límites de zoom. Más allá, la isometría deja de leerse. */
export const LIMITES = {
  /** Debajo de esto el mobiliario es una mancha y el texto no se lee. */
  escalaMin: 0.4,
  /** Por encima, un píxel de mundo ocupa tres y se ve el serrucho. */
  escalaMax: 2.6,
  /** Cuánto cambia la escala por cada muesca de la rueda. */
  pasoRueda: 0.0016,
  /** Margen de mundo que se deja ver fuera del recinto, en píxeles. */
  margen: 160
};

/**
 * Lo que separa un clic de un arrastre.
 *
 * 6 píxeles y 350 ms no son arbitrarios: un clic con el pulso normal mueve el
 * puntero 2-4 px, y un arrastre deliberado pasa de 10 al primer cuadro. El
 * umbral de tiempo es el que cubre el caso raro —mantener pulsado quieto y
 * soltar— que sin él se contaría como clic un segundo y medio después.
 */
export const GESTO = { radioClic: 6, msClic: 350 };

export interface Vista {
  ancho: number;
  alto: number;
}

export interface Extension {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  ancho: number;
  alto: number;
  centro: { x: number; y: number };
}

/** Lo que la escena le aplica a su contenedor. */
export interface Transformacion {
  x: number;
  y: number;
  escala: number;
}

/**
 * Acota la escala a los límites. Una función de una línea con nombre propio,
 * porque llamarla en los tres sitios que cambian el zoom es lo que impide que
 * uno de ellos se olvide.
 */
export function acotarEscala(escala: number, limites = LIMITES): number {
  if (!Number.isFinite(escala)) return 1;
  return Math.min(limites.escalaMax, Math.max(limites.escalaMin, escala));
}

/**
 * La escala que deja el recinto completo dentro de la vista, con aire.
 *
 * Se usa al entrar y al pulsar «encuadrar». El 0.9 es el aire: encajar al
 * milímetro deja el recinto tocando los cuatro bordes y la escena parece
 * recortada aunque esté entera.
 */
export function escalaDeEncuadre(ext: Extension, vista: Vista, limites = LIMITES): number {
  if (!vista.ancho || !vista.alto || !ext.ancho || !ext.alto) return 1;
  const porAncho = (vista.ancho * 0.9) / ext.ancho;
  const porAlto = (vista.alto * 0.9) / ext.alto;
  return acotarEscala(Math.min(porAncho, porAlto), limites);
}

/**
 * Nueva escala a partir de una muesca de rueda.
 *
 * El zoom es MULTIPLICATIVO, no aditivo: sumar un paso fijo hace que acercarse
 * desde lejos sea lentísimo y desde cerca brutal. Multiplicar da el mismo
 * recorrido percibido en todo el rango, que es lo que se espera de un zoom.
 */
export function escalaTrasRueda(escala: number, deltaY: number, limites = LIMITES): number {
  const factor = Math.exp(-deltaY * limites.pasoRueda);
  return acotarEscala(escala * factor, limites);
}

/**
 * Acota el centro para que el recinto no se escape de la vista.
 *
 * Sin esto, dos arrastres largos dejan la pantalla en negro y el único remedio
 * es recargar: no hay forma de saber hacia dónde volver, porque no se ve nada
 * que sirva de referencia. El margen permite asomarse un poco al vacío —da
 * sensación de espacio— pero no perder el recinto de vista.
 */
export function acotarCentro(
  centro: { x: number; y: number },
  escala: number,
  ext: Extension,
  vista: Vista,
  limites = LIMITES
): { x: number; y: number } {
  const medioAncho = vista.ancho / (2 * escala);
  const medioAlto = vista.alto / (2 * escala);
  const m = limites.margen;

  // Si el recinto cabe de sobra, se queda centrado: permitir arrastre cuando
  // todo se ve ya no es libertad, es que la escena se vaya sin motivo.
  const x =
    ext.ancho + m * 2 <= medioAncho * 2
      ? ext.centro.x
      : Math.min(Math.max(centro.x, ext.minX - m + medioAncho), ext.maxX + m - medioAncho);
  const y =
    ext.alto + m * 2 <= medioAlto * 2
      ? ext.centro.y
      : Math.min(Math.max(centro.y, ext.minY - m + medioAlto), ext.maxY + m - medioAlto);
  return { x, y };
}

/** Un punto del puntero, con el instante en que ocurrió. */
export interface Toque {
  x: number;
  y: number;
  t: number;
}

/**
 * ¿Fue un clic o un arrastre?
 *
 * Esta es la función que el defecto de `setPointerCapture` reclamaba. La escena
 * captura el puntero para que el arrastre siga funcionando fuera del lienzo
 * —eso está bien y es necesario— y al soltar pregunta acá. Si fue un clic, la
 * selección se emite a mano; el `click` del navegador ya no hace falta, así que
 * da igual que la captura se lo haya comido.
 */
export function gesto(inicio: Toque, fin: Toque, umbrales = GESTO): 'clic' | 'arrastre' {
  const dx = fin.x - inicio.x;
  const dy = fin.y - inicio.y;
  const distancia = Math.sqrt(dx * dx + dy * dy);
  if (distancia > umbrales.radioClic) return 'arrastre';
  if (fin.t - inicio.t > umbrales.msClic) return 'arrastre';
  return 'clic';
}

/**
 * Suavizado exponencial independiente del fotograma.
 *
 * `destino * k + actual * (1-k)` con k fijo parece suave a 60 fps y se arrastra
 * a 30: el mismo código da dos velocidades distintas según la máquina. La forma
 * correcta usa el tiempo transcurrido, y entonces el movimiento dura lo mismo
 * en cualquier equipo. Medirlo en una sola máquina es exactamente cómo este
 * error sobrevive.
 */
export function suavizar(actual: number, destino: number, dt: number, tau = 0.12): number {
  if (tau <= 0) return destino;
  const k = 1 - Math.exp(-dt / tau);
  return actual + (destino - actual) * k;
}

/**
 * La cámara con estado. Guarda a dónde mira y hacia dónde va, y entrega la
 * transformación ya acotada.
 */
export class Camara {
  private ext: Extension;
  private vista: Vista;
  private limites: typeof LIMITES;

  /** Dónde está ahora (lo que se dibuja). */
  private actual: Transformacion;
  /** Dónde quiere estar (a dónde lo llevó el gesto). */
  private destino: { x: number; y: number; escala: number };

  constructor(ext: Extension, vista: Vista, limites = LIMITES) {
    this.ext = ext;
    this.vista = vista;
    this.limites = limites;
    const escala = escalaDeEncuadre(ext, vista, limites);
    const centro = acotarCentro(ext.centro, escala, ext, vista, limites);
    this.actual = { x: centro.x, y: centro.y, escala };
    this.destino = { ...this.actual };
  }

  /** El tamaño de la vista cambió (la ventana, el panel lateral). */
  redimensionar(vista: Vista) {
    this.vista = vista;
    this.encuadrar();
  }

  /** Vuelve a dejar el recinto completo a la vista. */
  encuadrar() {
    const escala = escalaDeEncuadre(this.ext, this.vista, this.limites);
    const centro = acotarCentro(this.ext.centro, escala, this.ext, this.vista, this.limites);
    this.destino = { x: centro.x, y: centro.y, escala };
  }

  /**
   * Zoom con la rueda, anclado al puntero.
   *
   * Anclar al puntero es la diferencia entre un zoom usable y uno que marea:
   * sin ancla, acercarse mueve el punto de interés fuera de la pantalla y hay
   * que recolocar con el arrastre después de cada muesca.
   */
  rueda(deltaY: number, punteroVista: { x: number; y: number }) {
    const antes = this.destino.escala;
    const despues = escalaTrasRueda(antes, deltaY, this.limites);
    if (despues === antes) return;

    // El punto de mundo bajo el puntero antes del zoom tiene que seguir bajo el
    // puntero después.
    const offX = (punteroVista.x - this.vista.ancho / 2) / antes;
    const offY = (punteroVista.y - this.vista.alto / 2) / antes;
    const mundoX = this.destino.x + offX;
    const mundoY = this.destino.y + offY;

    const nuevoX = mundoX - (punteroVista.x - this.vista.ancho / 2) / despues;
    const nuevoY = mundoY - (punteroVista.y - this.vista.alto / 2) / despues;
    const centro = acotarCentro({ x: nuevoX, y: nuevoY }, despues, this.ext, this.vista, this.limites);
    this.destino = { x: centro.x, y: centro.y, escala: despues };
  }

  /**
   * Arrastre, en píxeles de pantalla.
   *
   * Se divide por la escala porque el arrastre se siente en pantalla: mover el
   * ratón 10 px tiene que mover la escena 10 px vistos, no 10 px de mundo. Sin
   * esa división, arrastrar con el zoom al máximo lanza la escena al infinito.
   */
  arrastrar(dxVista: number, dyVista: number) {
    const x = this.destino.x - dxVista / this.destino.escala;
    const y = this.destino.y - dyVista / this.destino.escala;
    const centro = acotarCentro({ x, y }, this.destino.escala, this.ext, this.vista, this.limites);
    this.destino = { ...this.destino, x: centro.x, y: centro.y };
  }

  /** Lleva la cámara a un punto de mundo sin cambiar el zoom. */
  mirarA(punto: { x: number; y: number }) {
    const centro = acotarCentro(punto, this.destino.escala, this.ext, this.vista, this.limites);
    this.destino = { ...this.destino, x: centro.x, y: centro.y };
  }

  /** Avanza el suavizado. `dt` en segundos. */
  avanzar(dt: number) {
    this.actual = {
      x: suavizar(this.actual.x, this.destino.x, dt),
      y: suavizar(this.actual.y, this.destino.y, dt),
      escala: suavizar(this.actual.escala, this.destino.escala, dt, 0.1)
    };
  }

  /** Lo que la escena le aplica a su contenedor raíz. */
  transformacion(): Transformacion {
    return {
      escala: this.actual.escala,
      x: this.vista.ancho / 2 - this.actual.x * this.actual.escala,
      y: this.vista.alto / 2 - this.actual.y * this.actual.escala
    };
  }

  /** Para las pruebas y para el panel de rendimiento. */
  estado() {
    return { actual: { ...this.actual }, destino: { ...this.destino } };
  }
}
