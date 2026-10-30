/**
 * EL RECINTO: suelo, muros, mobiliario y el mural de pantallas.
 *
 * No sabe nada de lo que pasa en la empresa. Recibe una lista de puestos con su
 * posición y devuelve un contenedor dibujado más un `animar(t, dt)` para lo que
 * se mueve por sí solo —las pantallas del mural, los testigos de los equipos,
 * la luz—. Quién ocupa cada puesto y qué está haciendo lo decide `adaptador.ts`;
 * acá no hay una sola palabra de negocio, y hay una prueba que lo comprueba.
 *
 * TODO ESTÁ DIBUJADO, NO IMPORTADO
 * No hay sprites ni atlas: cada volumen son tres caras —tapa iluminada, canto en
 * penumbra, lateral en sombra— derivadas del mismo color base con `tono()`. Es
 * la técnica que hace que una escena sin arte se lea como volumen y no como
 * recortes de papel, y tiene una ventaja que el arte no da: la luz entra SIEMPRE
 * del mismo lado, porque el signo está en una sola función.
 *
 * LO QUE NO ES, Y CONVIENE DECIRLO
 * Esto no es arte definitivo. Es una escena construida con geometría para fijar
 * la composición, la escala, la profundidad y el rendimiento. El día que haya
 * ilustración, lo que se reemplaza es el cuerpo de estas funciones: la rejilla,
 * el orden de pintado, la cámara y la frontera con los datos no se tocan. Ese
 * reparto es el verdadero entregable.
 *
 * EL ORDEN DE PINTADO ES UNA DECISIÓN, NO UN DESCUIDO
 * `sortableChildren` con `zIndex = profundidad(gx, gy)` para el mobiliario, y
 * dos valores fijos muy negativos para el suelo y los muros. Los muros están en
 * `gx = 0` y `gy = 0` y el mobiliario siempre en `gx >= 1, gy >= 1`, así que
 * ninguna pieza puede quedar DETRÁS de un muro por un empate de profundidad —
 * que es el defecto que aparece como un parpadeo entre fotogramas y se busca
 * durante una hora en el sitio equivocado.
 */

import { Container, Graphics, Sprite, Text, Polygon } from 'pixi.js';
import { ALTURA_UNIDAD, BALDOSA, aPantalla, profundidad, rombo, type Mundo } from './isometria';
import { PALETA, tono } from './paleta';
import type { Texturas } from './texturas';

/** El recinto del primer prototipo. Un NOC, y nada más. */
export const MUNDO: Mundo = { ancho: 14, fondo: 10, alto: 4 };

/** El pasillo: una franja de suelo más clara que cruza el recinto. */
const PASILLO = { desde: 11, hasta: 14 };

/** Declaración de un puesto. Posición y a quién pertenece, nada más. */
export interface DefinicionDePuesto {
  id: string;
  /** El agente que lo ocupa, o `null` si está vacío. */
  agente: string | null;
  /** Lo que se lee en la placa del puesto. */
  nombre: string;
  /** El área, para la placa. Dato de la empresa, no de la escena. */
  area: string;
  gx: number;
  gy: number;
  /** Un puesto principal es más grande y lleva tres monitores. */
  principal?: boolean;
}

export interface Puesto {
  def: DefinicionDePuesto;
  nodo: Container;
  /** Donde se monta el personaje. Vacío si el puesto no tiene agente. */
  ancla: Container;
  /** El halo de estado en el suelo. Se tiñe y se gradúa. */
  halo: Sprite;
  /**
   * Las piezas que emiten luz en el puesto, con la opacidad que les toca
   * cuando el brillo es 1. Se guardan en una lista en vez de aplicarle `alpha`
   * al contenedor: el marco del monitor no emite luz y bajarle la opacidad lo
   * volvería translúcido, con el escritorio visible a través.
   */
  brillos: { pieza: Container; base: number }[];
  /** El rótulo de la actividad bajo la placa. */
  rotulo: Text;
  /** El punto de color del estado en la placa. */
  testigo: Graphics;
  /** El marco que aparece al seleccionar. */
  seleccion: Graphics;
  /** El paquete que sale del puesto cuando algo se despacha. */
  paquete: Container;
}

export interface Oficina {
  raiz: Container;
  mundo: Mundo;
  puestos: Puesto[];
  /** Lo que se mueve por sí solo. `t` acumulado y `dt`, en segundos. */
  animar(t: number, dt: number): void;
  destruir(): void;
}

/* ════════════════════════════════════════════════════════════════════════════
   Piezas elementales
   ════════════════════════════════════════════════════════════════════════════ */

/**
 * Una caja isométrica: tapa, canto derecho y canto izquierdo.
 *
 * Es la pieza con la que está hecho el 80% del mobiliario. Los dos cantos se
 * derivan de la tapa (-18% y -34%): declararlos a mano para cada mueble es cómo
 * termina habiendo un escritorio iluminado desde la izquierda en una sala
 * iluminada desde la derecha.
 */
function caja(
  g: Graphics,
  gx: number,
  gy: number,
  gz: number,
  ancho: number,
  fondo: number,
  alto: number,
  color: number
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
  g.poly(aplanar(i)).fill({ color: tono(color, -0.34) });
  g.poly(aplanar(d)).fill({ color: tono(color, -0.18) });
  g.poly(aplanar(t)).fill({ color });
}

function aplanar(puntos: { x: number; y: number }[]): number[] {
  const salida: number[] = [];
  for (const p of puntos) salida.push(p.x, p.y);
  return salida;
}

/**
 * Un panel plano pegado al muro de `gy = 0`, visto de frente.
 *
 * Las coordenadas son (gx, altura) porque un panel de pared no tiene fondo. Hay
 * una función por muro y no una genérica con un parámetro de orientación: la
 * versión genérica es la que termina con un panel espejado, y un texto espejado
 * dentro de una pared oscura no se ve en una captura.
 */
function panelMuroFondo(
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
function panelMuroLateral(
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

/* ════════════════════════════════════════════════════════════════════════════
   El recinto
   ════════════════════════════════════════════════════════════════════════════ */

function construirSuelo(mundo: Mundo): Container {
  const capa = new Container();
  const g = new Graphics();
  capa.addChild(g);

  for (let gx = 0; gx < mundo.ancho; gx++) {
    for (let gy = 0; gy < mundo.fondo; gy++) {
      const enPasillo = gx >= PASILLO.desde && gx < PASILLO.hasta;
      const base = enPasillo ? PALETA.pisoPasillo : (gx + gy) % 2 === 0 ? PALETA.pisoA : PALETA.pisoB;
      // Oscurecer al fondo: la perspectiva aérea aplicada al interior de una
      // sala. Es lo que da sensación de profundidad sin mover la cámara.
      const lejania = 1 - (gx + gy) / (mundo.ancho + mundo.fondo);
      g.poly(aplanar(rombo(gx, gy))).fill({ color: tono(base, -0.22 * lejania) });
    }
  }

  // Las juntas, en una sola pasada y por líneas completas: 24 trazos en vez de
  // 140 rombos con borde. A ojo es idéntico.
  for (let gx = 0; gx <= mundo.ancho; gx++) {
    const a = aPantalla(gx, 0);
    const b = aPantalla(gx, mundo.fondo);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  for (let gy = 0; gy <= mundo.fondo; gy++) {
    const a = aPantalla(0, gy);
    const b = aPantalla(mundo.ancho, gy);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 1, color: PALETA.junta, alpha: 0.55 });

  // Marcas del pasillo: dos líneas continuas y trazos cortos entre ellas. Es lo
  // que convierte una franja de color en un paso.
  const marcas = new Graphics();
  for (const borde of [PASILLO.desde, PASILLO.hasta]) {
    const a = aPantalla(borde, 0);
    const b = aPantalla(borde, mundo.fondo);
    marcas.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  marcas.stroke({ width: 2, color: PALETA.clayClaro, alpha: 0.22 });
  for (let gy = 0.4; gy < mundo.fondo; gy += 1.4) {
    const a = aPantalla((PASILLO.desde + PASILLO.hasta) / 2, gy);
    const b = aPantalla((PASILLO.desde + PASILLO.hasta) / 2, gy + 0.6);
    marcas.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  marcas.stroke({ width: 2, color: PALETA.clayClaro, alpha: 0.16 });
  // Hermano, no hijo: un `Graphics` dentro de otro `Graphics` funciona y el
  // motor avisa por consola, con razón — son dos cosas distintas (una figura y
  // un contenedor) y mezclarlas hace que `clear()` del padre no haga lo que
  // parece. La capa cuesta un objeto y quita el aviso.
  capa.addChild(marcas);

  return capa;
}

function construirMuros(mundo: Mundo): Graphics {
  const g = new Graphics();
  const h = mundo.alto;

  // Muro de fondo (gy = 0) y muro lateral (gx = 0), cada uno con su propio tono:
  // el lateral recibe menos luz. Pintar los dos iguales es lo que hace que la
  // esquina desaparezca y la sala parezca un telón.
  panelMuroFondo(g, 0, mundo.ancho, 0, h, PALETA.muroFondo);
  panelMuroLateral(g, 0, mundo.fondo, 0, h, PALETA.muroLateral);

  // Sombra de contacto al pie de cada muro: sin esto los muros flotan y el
  // síntoma se describe como «la escena se ve plana».
  panelMuroFondo(g, 0, mundo.ancho, 0, 0.45, PALETA.pisoProfundo, 0.75);
  panelMuroLateral(g, 0, mundo.fondo, 0, 0.45, PALETA.pisoProfundo, 0.75);

  // Banda de luz indirecta a media altura. Es el detalle más rentable de toda
  // la escena: dos rectángulos y la pared deja de ser un plano de color.
  panelMuroFondo(g, 0, mundo.ancho, 1.02, 1.1, PALETA.muroBanda, 0.9);
  panelMuroLateral(g, 0, mundo.fondo, 1.02, 1.1, PALETA.muroBanda, 0.9);

  // Remate superior, con su canto: lo que le da espesor al muro.
  panelMuroFondo(g, 0, mundo.ancho, h - 0.12, h, PALETA.muroRemate);
  panelMuroLateral(g, 0, mundo.fondo, h - 0.12, h, PALETA.muroRemate);

  // Bandeja de cables bajo el remate, en el muro lateral. Son tres líneas y
  // dicen «esto es una sala técnica» más que cualquier otra cosa.
  for (let i = 0; i < 3; i++) {
    const z = h - 0.45 - i * 0.1;
    const a = aPantalla(0, 0.3, z);
    const b = aPantalla(0, mundo.fondo - 0.3, z);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 2, color: PALETA.metal, alpha: 0.5 });

  return g;
}

/* ════════════════════════════════════════════════════════════════════════════
   El mural de pantallas
   ════════════════════════════════════════════════════════════════════════════ */

interface Mural {
  nodo: Container;
  animar(t: number, dt: number): void;
}

/**
 * Las tres pantallas grandes del muro de fondo.
 *
 * Cada una muestra una cosa distinta porque tres pantallas idénticas se leen
 * como un patrón decorativo. Y las tres se mueven: una pantalla quieta delata
 * que la escena está congelada, y es lo primero que alguien nota.
 *
 * NADA DE ESTO ES UN DATO. Es forma: barras, nodos, un barrido. No lleva cifras
 * ni nombres, y es a propósito — una pantalla de adorno con un número encima se
 * lee como una medición, y en cuanto alguien la cree, la escena está mintiendo.
 */
function construirMural(texturas: Texturas): Mural {
  const nodo = new Container();
  const anim: ((t: number, dt: number) => void)[] = [];

  const paneles = [
    { gx: 2.6, ancho: 3.0 },
    { gx: 5.9, ancho: 3.0 },
    { gx: 9.2, ancho: 3.0 }
  ];
  const z0 = 1.45;
  const z1 = 3.35;

  paneles.forEach((p, indice) => {
    const marco = new Graphics();
    panelMuroFondo(marco, p.gx - 0.1, p.ancho + 0.2, z0 - 0.1, z1 + 0.1, PALETA.pantallaMarco);
    panelMuroFondo(marco, p.gx, p.ancho, z0, z1, tono(PALETA.ember, -0.78));
    nodo.addChild(marco);

    // La trama, recortada al panel. Le da estructura a un rectángulo brillante,
    // que es lo que lo hace leerse como monitor y no como un cartel.
    const esquina = aPantalla(p.gx, 0, z1);
    const trama = new Sprite(texturas.trama);
    trama.x = esquina.x;
    trama.y = esquina.y;
    trama.width = p.ancho * BALDOSA.ancho * 0.5;
    trama.height = (z1 - z0) * ALTURA_UNIDAD;
    trama.alpha = 0.5;
    // El muro de fondo se ve en diagonal: la trama tiene que seguir esa
    // inclinación o se nota pegada encima.
    trama.skew.y = Math.atan2(BALDOSA.alto / 2, BALDOSA.ancho / 2);
    nodo.addChild(trama);

    const contenido = new Container();
    nodo.addChild(contenido);

    if (indice === 0) anim.push(muralDeBarras(contenido, p.gx, p.ancho, z0, z1));
    else if (indice === 1) anim.push(muralDeEnlaces(contenido, p.gx, p.ancho, z0, z1));
    else anim.push(muralDeBarrido(contenido, p.gx, p.ancho, z0, z1, texturas));

    // El resplandor que la pantalla echa sobre el muro y el suelo. Es lo que
    // hace que la luz pertenezca a la escena en vez de estar dentro del marco.
    const luz = new Sprite(texturas.halo);
    luz.anchor.set(0.5);
    const centro = aPantalla(p.gx + p.ancho / 2, 0, (z0 + z1) / 2);
    luz.position.set(centro.x, centro.y);
    luz.width = p.ancho * BALDOSA.ancho * 1.5;
    luz.height = (z1 - z0) * ALTURA_UNIDAD * 3.2;
    luz.tint = PALETA.emberClaro;
    luz.blendMode = 'add';
    luz.alpha = 0.16;
    nodo.addChild(luz);
    anim.push((t) => {
      luz.alpha = 0.13 + Math.sin(t * 0.7 + indice) * 0.03;
    });
  });

  return {
    nodo,
    animar(t, dt) {
      for (const f of anim) f(t, dt);
    }
  };
}

/** Panel 1: barras verticales que suben y bajan. */
function muralDeBarras(padre: Container, gx: number, ancho: number, z0: number, z1: number) {
  const barras: { g: Graphics; fase: number; alto: number }[] = [];
  const n = 11;
  for (let i = 0; i < n; i++) {
    const bx = gx + 0.18 + (i * (ancho - 0.36)) / n;
    const bw = (ancho - 0.36) / n - 0.045;
    const g = new Graphics();
    panelMuroFondo(g, bx, bw, z0 + 0.18, z1 - 0.3, PALETA.emberClaro, 0.85);
    // El pivote de la escala está en la base de la barra, no en el origen del
    // panel: escalar desde el origen hunde las barras en el suelo.
    const base = aPantalla(bx, 0, z0 + 0.18);
    g.pivot.set(0, base.y);
    g.y = base.y;
    padre.addChild(g);
    barras.push({ g, fase: i * 0.7, alto: z1 - z0 });
  }
  return (t: number) => {
    for (const b of barras) {
      const v = 0.25 + (Math.sin(t * 1.1 + b.fase) * 0.5 + 0.5) * 0.7;
      b.g.scale.y = v;
      b.g.tint = v > 0.82 ? PALETA.clayClaro : 0xffffff;
    }
  };
}

/** Panel 2: nodos unidos por enlaces, con un pulso que viaja. */
function muralDeEnlaces(padre: Container, gx: number, ancho: number, z0: number, z1: number) {
  const nodos = [
    { x: 0.5, z: 0.5 },
    { x: 0.22, z: 0.75 },
    { x: 0.78, z: 0.74 },
    { x: 0.16, z: 0.3 },
    { x: 0.5, z: 0.2 },
    { x: 0.84, z: 0.32 },
    { x: 0.35, z: 0.52 },
    { x: 0.66, z: 0.5 }
  ];
  const enlaces: [number, number][] = [
    [0, 1],
    [0, 2],
    [0, 4],
    [0, 6],
    [0, 7],
    [1, 3],
    [2, 5],
    [4, 5],
    [3, 4],
    [6, 1],
    [7, 2]
  ];
  const punto = (n: { x: number; z: number }) =>
    aPantalla(gx + 0.2 + n.x * (ancho - 0.4), 0, z0 + 0.25 + n.z * (z1 - z0 - 0.5));

  const lineas = new Graphics();
  for (const [a, b] of enlaces) {
    const pa = punto(nodos[a]);
    const pb = punto(nodos[b]);
    lineas.moveTo(pa.x, pa.y).lineTo(pb.x, pb.y);
  }
  lineas.stroke({ width: 1.4, color: PALETA.emberClaro, alpha: 0.45 });
  padre.addChild(lineas);

  const puntos: Graphics[] = [];
  nodos.forEach((n, i) => {
    const p = punto(n);
    const g = new Graphics();
    g.circle(0, 0, i === 0 ? 4.2 : 2.6).fill({ color: i === 0 ? PALETA.clayClaro : PALETA.emberClaro });
    g.position.set(p.x, p.y);
    padre.addChild(g);
    puntos.push(g);
  });

  // El pulso: un punto que recorre un enlace y salta al siguiente. Es lo que
  // hace que un grafo quieto parezca una red con tráfico.
  const pulso = new Graphics();
  pulso.circle(0, 0, 2.2).fill({ color: 0xffffff });
  padre.addChild(pulso);

  return (t: number) => {
    const total = enlaces.length;
    const recorrido = (t * 0.55) % total;
    const indice = Math.floor(recorrido);
    const k = recorrido - indice;
    const [a, b] = enlaces[indice];
    const pa = punto(nodos[a]);
    const pb = punto(nodos[b]);
    pulso.position.set(pa.x + (pb.x - pa.x) * k, pa.y + (pb.y - pa.y) * k);
    pulso.alpha = 0.55 + Math.sin(k * Math.PI) * 0.45;
    puntos.forEach((g, i) => {
      g.scale.set(1 + Math.sin(t * 2.2 + i * 1.3) * 0.12);
      g.alpha = 0.7 + Math.sin(t * 1.7 + i) * 0.3;
    });
  };
}

/** Panel 3: una traza continua con un barrido que la recorre. */
function muralDeBarrido(
  padre: Container,
  gx: number,
  ancho: number,
  z0: number,
  z1: number,
  texturas: Texturas
) {
  const n = 46;
  const traza = new Graphics();
  padre.addChild(traza);

  const barrido = new Sprite(texturas.haz);
  barrido.anchor.set(0.5, 0);
  barrido.width = 18;
  barrido.height = (z1 - z0 - 0.3) * ALTURA_UNIDAD;
  barrido.tint = PALETA.mossClaro;
  barrido.blendMode = 'add';
  barrido.alpha = 0.5;
  barrido.skew.x = -Math.atan2(BALDOSA.alto / 2, BALDOSA.ancho / 2);
  padre.addChild(barrido);

  // La línea base: una referencia horizontal. Sin ella la traza no tiene
  // respecto a qué subir ni bajar, y se lee como un garabato.
  const base = new Graphics();
  panelMuroFondo(base, gx + 0.2, ancho - 0.4, z0 + 0.95, z0 + 0.97, PALETA.textoTenue, 0.3);
  padre.addChild(base);

  return (t: number) => {
    traza.clear();
    for (let i = 0; i < n; i++) {
      const px = gx + 0.2 + (i * (ancho - 0.4)) / (n - 1);
      const onda =
        Math.sin(i * 0.5 + t * 1.6) * 0.3 + Math.sin(i * 0.17 - t * 0.9) * 0.2 + Math.sin(i * 1.3 + t * 3) * 0.08;
      const pz = z0 + 0.95 + onda;
      const p = aPantalla(px, 0, pz);
      if (i === 0) traza.moveTo(p.x, p.y);
      else traza.lineTo(p.x, p.y);
    }
    traza.stroke({ width: 1.8, color: PALETA.mossClaro, alpha: 0.9 });

    const avance = (t * 0.22) % 1;
    const p = aPantalla(gx + 0.2 + avance * (ancho - 0.4), 0, z1 - 0.15);
    barrido.position.set(p.x, p.y);
  };
}

/* ════════════════════════════════════════════════════════════════════════════
   Mobiliario técnico
   ════════════════════════════════════════════════════════════════════════════ */

interface Mueble {
  nodo: Container;
  animar?(t: number, dt: number): void;
}

/** Un armario de equipos contra el muro lateral, con sus testigos. */
function construirArmario(gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.4, gy);

  const g = new Graphics();
  caja(g, 0.1, gy, 0, 0.75, 1.5, 3.1, PALETA.rackCuerpo);
  // El frente, con sus bandejas. Las ranuras son lo que lo distingue de una
  // caja: sin ellas es un bloque.
  for (let i = 0; i < 9; i++) {
    const z = 0.22 + i * 0.32;
    panelMuroLateral(g, gy + 0.08, 1.34, z, z + 0.24, PALETA.rackFrente);
  }
  nodo.addChild(g);

  const testigos: Graphics[] = [];
  for (let i = 0; i < 9; i++) {
    for (let j = 0; j < 2; j++) {
      const p = aPantalla(0.1, gy + 0.22 + j * 0.22, 0.34 + i * 0.32);
      const led = new Graphics();
      led.circle(0, 0, 1.5).fill({ color: j === 0 ? PALETA.mossClaro : PALETA.emberClaro });
      led.position.set(p.x, p.y);
      nodo.addChild(led);
      testigos.push(led);
    }
  }

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  const pie = aPantalla(0.48, gy + 0.75, 0);
  sombra.position.set(pie.x, pie.y);
  sombra.width = 95;
  sombra.height = 48;
  sombra.alpha = 0.6;
  nodo.addChildAt(sombra, 0);

  return {
    nodo,
    animar(t) {
      // Los testigos no parpadean al unísono: eso se lee como una guirnalda.
      // Cada uno con su fase, y uno de cada siete se queda apagado un rato.
      for (let i = 0; i < testigos.length; i++) {
        const fase = i * 2.39;
        const v = Math.sin(t * (3 + (i % 5)) + fase);
        testigos[i].alpha = i % 7 === 3 ? 0.12 + Math.max(0, v) * 0.2 : 0.4 + Math.max(0, v) * 0.6;
      }
    }
  };
}

/** El panel de empalmes: una rejilla de bocas con hebras que salen de ellas. */
function construirPanelDeFibra(gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.3, gy);

  const g = new Graphics();
  panelMuroLateral(g, gy, 2.1, 1.35, 2.5, PALETA.pantallaMarco);
  panelMuroLateral(g, gy + 0.08, 1.94, 1.45, 2.4, tono(PALETA.rackFrente, 0.08));
  nodo.addChild(g);

  // Las bocas. 2 filas × 12: una rejilla regular es exactamente lo que es un
  // panel de empalmes, así que acá la regularidad sí corresponde.
  const bocas = new Graphics();
  for (let fila = 0; fila < 2; fila++) {
    for (let i = 0; i < 12; i++) {
      const p = aPantalla(0, gy + 0.2 + i * 0.15, 2.22 - fila * 0.38);
      bocas.circle(p.x, p.y, 1.7).fill({ color: PALETA.pisoProfundo });
      bocas.circle(p.x, p.y, 0.9).fill({ color: (i + fila) % 3 === 0 ? PALETA.clayClaro : PALETA.mossClaro });
    }
  }
  nodo.addChild(bocas);

  // Las hebras: curvas que caen del panel y entran en la bandeja. Dibujadas con
  // cuadráticas, que es lo que hace que un cable parezca colgar en vez de ser
  // una línea recta diagonal.
  const hebras = new Graphics();
  for (let i = 0; i < 7; i++) {
    const a = aPantalla(0, gy + 0.25 + i * 0.26, 1.45);
    const b = aPantalla(0, gy + 0.1 + i * 0.3, 0.55);
    hebras.moveTo(a.x, a.y).quadraticCurveTo(a.x - 10, a.y + 28, b.x, b.y);
  }
  hebras.stroke({ width: 1.3, color: PALETA.emberClaro, alpha: 0.4 });
  nodo.addChild(hebras);

  return { nodo };
}

/** Una luminaria de techo con su haz. Es la luz «de la sala». */
function construirLuminaria(gx: number, gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy) - 0.5;

  const charco = new Sprite(texturas.halo);
  charco.anchor.set(0.5);
  const suelo = aPantalla(gx, gy, 0);
  charco.position.set(suelo.x, suelo.y);
  charco.width = 330;
  charco.height = 165;
  charco.tint = 0xcfd6ff;
  charco.blendMode = 'add';
  charco.alpha = 0.075;
  nodo.addChild(charco);

  const g = new Graphics();
  caja(g, gx - 0.6, gy - 0.25, 3.85, 1.2, 0.5, 0.12, PALETA.metal);
  nodo.addChild(g);

  return {
    nodo,
    animar(t) {
      // Una luminaria perfectamente estable es correcta y muerta. Un 2% de
      // variación lenta es lo que la vuelve luz.
      charco.alpha = 0.07 + Math.sin(t * 0.4 + gx) * 0.012;
    }
  };
}

/** Una planta. El detalle que más humaniza una sala técnica. */
function construirPlanta(gx: number, gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  const suelo = aPantalla(gx + 0.3, gy + 0.3, 0);
  sombra.position.set(suelo.x, suelo.y);
  sombra.width = 62;
  sombra.height = 31;
  sombra.alpha = 0.55;
  nodo.addChild(sombra);

  const g = new Graphics();
  caja(g, gx + 0.08, gy + 0.08, 0, 0.45, 0.45, 0.42, PALETA.maceta);
  nodo.addChild(g);

  const hojas = new Container();
  const centro = aPantalla(gx + 0.3, gy + 0.3, 0.42);
  hojas.position.set(centro.x, centro.y);
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2 + 0.3;
    const largo = 20 + (i % 3) * 7;
    const hoja = new Graphics();
    hoja
      .moveTo(0, 0)
      .quadraticCurveTo(Math.cos(a) * largo * 0.5, -largo * 0.75, Math.cos(a) * largo, -largo * 0.5)
      .quadraticCurveTo(Math.cos(a) * largo * 0.45, -largo * 0.42, 0, 0)
      .fill({ color: i % 2 === 0 ? PALETA.planta : PALETA.plantaOscura });
    hojas.addChild(hoja);
  }
  nodo.addChild(hojas);

  return {
    nodo,
    animar(t) {
      // Las hojas se mecen muy poco. Mucho es una palmera en un huracán dentro
      // de una sala cerrada, y se nota como un error.
      hojas.skew.x = Math.sin(t * 0.6 + gx) * 0.02;
    }
  };
}

/** Un banco del pasillo. */
function construirBanco(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();
  caja(g, gx, gy + 0.1, 0.35, 2.2, 0.5, 0.1, PALETA.escritorioTapa);
  caja(g, gx + 0.1, gy + 0.18, 0, 0.14, 0.34, 0.35, PALETA.escritorioPata);
  caja(g, gx + 1.96, gy + 0.18, 0, 0.14, 0.34, 0.35, PALETA.escritorioPata);
  nodo.addChild(g);
  return { nodo };
}

/** Un dispensador de agua. */
function construirDispensador(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();
  caja(g, gx, gy, 0, 0.5, 0.5, 1.05, PALETA.escritorioCanto);
  caja(g, gx + 0.08, gy + 0.08, 1.05, 0.34, 0.34, 0.5, 0x6f86c9);
  nodo.addChild(g);
  return { nodo };
}

/* ════════════════════════════════════════════════════════════════════════════
   El puesto de trabajo
   ════════════════════════════════════════════════════════════════════════════ */

function construirPuesto(def: DefinicionDePuesto, texturas: Texturas): Puesto {
  const nodo = new Container();
  nodo.zIndex = profundidad(def.gx, def.gy);
  nodo.sortableChildren = true;

  const ancho = def.principal ? 3.2 : 2.3;
  const monitores = def.principal ? 3 : 2;
  const brillos: { pieza: Container; base: number }[] = [];

  /* El halo del estado, debajo de todo: es luz en el suelo. */
  const halo = new Sprite(texturas.halo);
  halo.anchor.set(0.5);
  const pieHalo = aPantalla(def.gx + ancho / 2, def.gy + 0.4, 0);
  halo.position.set(pieHalo.x, pieHalo.y);
  halo.width = def.principal ? 340 : 250;
  halo.height = def.principal ? 170 : 125;
  halo.blendMode = 'add';
  halo.alpha = 0;
  halo.zIndex = -10;
  nodo.addChild(halo);

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  sombra.position.set(pieHalo.x, pieHalo.y + 6);
  sombra.width = ancho * 52;
  sombra.height = ancho * 26;
  sombra.alpha = 0.5;
  sombra.zIndex = -5;
  nodo.addChild(sombra);

  /* El escritorio. */
  const mueble = new Graphics();
  mueble.zIndex = 0;
  caja(mueble, def.gx, def.gy, 0.72, ancho, 1.0, 0.09, PALETA.escritorioTapa);
  // Las patas: dos bloques en los extremos, no cuatro palos. A esta escala
  // cuatro palos se pierden y cuestan lo mismo.
  caja(mueble, def.gx + 0.08, def.gy + 0.1, 0, 0.16, 0.8, 0.72, PALETA.escritorioPata);
  caja(mueble, def.gx + ancho - 0.24, def.gy + 0.1, 0, 0.16, 0.8, 0.72, PALETA.escritorioPata);
  // El faldón frontal: lo que cierra el hueco bajo la tapa y hace que el
  // escritorio no parezca una tabla flotando sobre dos tacos.
  caja(mueble, def.gx + 0.24, def.gy + 0.86, 0.18, ancho - 0.48, 0.08, 0.54, PALETA.escritorioCanto);
  nodo.addChild(mueble);

  /* El reflejo de las pantallas sobre la tapa. Es el detalle que delata que la
     luz de la escena viene de los monitores y no de ninguna parte. */
  const reflejo = new Sprite(texturas.haz);
  reflejo.anchor.set(0.5, 0);
  const tapa = aPantalla(def.gx + ancho / 2, def.gy + 0.45, 0.82);
  reflejo.position.set(tapa.x, tapa.y - 4);
  reflejo.width = ancho * 44;
  reflejo.height = 26;
  reflejo.tint = PALETA.emberClaro;
  reflejo.blendMode = 'add';
  reflejo.alpha = 0.2;
  reflejo.zIndex = 1;
  nodo.addChild(reflejo);
  brillos.push({ pieza: reflejo, base: 0.26 });

  /* Los monitores. Perfil bajo a propósito: el personaje se sienta DETRÁS, y
     una pantalla alta le taparía la cabeza. Esa restricción decidió la
     composición entera de la sala. */
  const pantallas = new Container();
  pantallas.zIndex = 2;
  for (let i = 0; i < monitores; i++) {
    const mx = def.gx + 0.35 + i * ((ancho - 0.7) / monitores);
    const mw = (ancho - 0.7) / monitores - 0.12;

    const marco = new Graphics();
    caja(marco, mx, def.gy + 0.2, 0.81, mw, 0.1, 0.78, PALETA.pantallaMarco);
    caja(marco, mx + mw / 2 - 0.07, def.gy + 0.22, 0.81, 0.14, 0.06, 0.12, PALETA.metal);
    pantallas.addChild(marco);

    // La cara que se ve es la de atrás (el personaje mira la otra). El vidrio
    // se insinúa por el borde superior, que es lo que se ve desde acá.
    const vidrio = new Graphics();
    const z0 = 0.95;
    const z1 = 1.59;
    const p = [
      aPantalla(mx + 0.01, def.gy + 0.2, z1),
      aPantalla(mx + mw - 0.01, def.gy + 0.2, z1),
      aPantalla(mx + mw - 0.01, def.gy + 0.2, z0),
      aPantalla(mx + 0.01, def.gy + 0.2, z0)
    ];
    vidrio.poly(aplanar(p)).fill({ color: PALETA.emberClaro });
    vidrio.blendMode = 'add';
    vidrio.alpha = 0.3;
    pantallas.addChild(vidrio);
    brillos.push({ pieza: vidrio, base: 0.42 });

    // El derrame por el borde superior: la luz que sale del vidrio hacia el
    // espectador. Un monitor visto de espaldas sin derrame se ve apagado.
    const derrame = new Sprite(texturas.halo);
    derrame.anchor.set(0.5);
    const borde = aPantalla(mx + mw / 2, def.gy + 0.2, z1);
    derrame.position.set(borde.x, borde.y);
    derrame.width = mw * 95;
    derrame.height = 56;
    derrame.tint = PALETA.emberClaro;
    derrame.blendMode = 'add';
    derrame.alpha = 0.35;
    pantallas.addChild(derrame);
    brillos.push({ pieza: derrame, base: 0.42 });
  }
  nodo.addChild(pantallas);

  /* El teclado y la taza. Dos piezas minúsculas que cambian mucho: un
     escritorio vacío se lee como mobiliario de catálogo. */
  const sobremesa = new Graphics();
  sobremesa.zIndex = 3;
  caja(sobremesa, def.gx + ancho / 2 - 0.55, def.gy + 0.56, 0.81, 1.1, 0.26, 0.03, tono(PALETA.escritorioCanto, 0.1));
  caja(sobremesa, def.gx + ancho / 2 + 0.62, def.gy + 0.6, 0.81, 0.18, 0.18, 0.16, PALETA.textoTenue);
  nodo.addChild(sobremesa);

  /* El paquete que sale del puesto al despachar algo. Oculto por defecto. */
  const paquete = new Container();
  paquete.zIndex = 20;
  const pg = new Graphics();
  caja(pg, 0, 0, 0, 0.34, 0.34, 0.22, PALETA.clayClaro);
  paquete.addChild(pg);
  const brilloPaquete = new Sprite(texturas.halo);
  brilloPaquete.anchor.set(0.5);
  brilloPaquete.width = 70;
  brilloPaquete.height = 50;
  brilloPaquete.tint = PALETA.clayClaro;
  brilloPaquete.blendMode = 'add';
  brilloPaquete.alpha = 0.5;
  paquete.addChildAt(brilloPaquete, 0);
  paquete.visible = false;
  nodo.addChild(paquete);

  /* El ancla del personaje: una celda detrás del escritorio. */
  const ancla = new Container();
  const puntoAncla = aPantalla(def.gx + ancho / 2, def.gy - 0.15, 0);
  ancla.position.set(puntoAncla.x, puntoAncla.y);
  // DETRÁS del escritorio, no delante. El personaje está más lejos de la
  // cámara, así que los monitores le tapan el tronco y se le ven la cabeza y
  // los hombros por encima. Esa oclusión no es un defecto: es la que decidió
  // toda la composición de la sala, y dibujarlo delante lo dejaría flotando
  // sobre su propia mesa.
  ancla.zIndex = -2;
  nodo.addChild(ancla);

  /* La placa con el nombre. Va SOBRE una placa opaca y no sobre el suelo: el
     contraste de un texto claro sobre un piso oscuro cambia según la baldosa, y
     eso es justo lo que la paleta del tablero ya tuvo que corregir una vez. */
  const placa = new Container();
  placa.zIndex = 30;
  const alturaPlaca = def.principal ? 3.0 : 2.45;
  const puntoPlaca = aPantalla(def.gx + ancho / 2, def.gy - 0.4, alturaPlaca);
  placa.position.set(puntoPlaca.x, puntoPlaca.y);

  const titulo = new Text({
    text: def.nombre,
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: 12,
      fontWeight: '600',
      fill: PALETA.textoClaro,
      letterSpacing: 0.2
    },
    resolution: 2
  });
  titulo.anchor.set(0.5, 1);
  const subtitulo = new Text({
    text: def.area,
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: 9.5,
      fill: PALETA.textoTenue,
      letterSpacing: 0.6
    },
    resolution: 2
  });
  subtitulo.anchor.set(0.5, 0);
  subtitulo.y = 2;

  const rotulo = new Text({
    text: '',
    style: {
      fontFamily: 'ui-monospace, SFMono-Regular, monospace',
      fontSize: 9.5,
      fill: PALETA.textoClaro,
      letterSpacing: 0.3
    },
    resolution: 2
  });
  rotulo.anchor.set(0.5, 0);
  rotulo.y = 16;
  rotulo.visible = false;

  const anchoPlaca = Math.max(titulo.width, subtitulo.width) + 26;
  const fondoPlaca = new Graphics();
  fondoPlaca
    .roundRect(-anchoPlaca / 2, -titulo.height - 5, anchoPlaca, titulo.height + subtitulo.height + 11, 4)
    .fill({ color: PALETA.placa, alpha: 0.86 })
    .stroke({ width: 1, color: 0xffffff, alpha: 0.08 });

  const testigo = new Graphics();
  testigo.circle(0, 0, 3).fill({ color: PALETA.ember });
  testigo.position.set(-anchoPlaca / 2 + 9, -titulo.height / 2 - 1);

  placa.addChild(fondoPlaca, testigo, titulo, subtitulo, rotulo);
  nodo.addChild(placa);

  /* El marco de selección. Un rombo en el suelo, no un recuadro: un recuadro
     recto sobre una escena isométrica se lee como parte de la interfaz, no de
     la sala. */
  const seleccion = new Graphics();
  seleccion.zIndex = -8;
  const contorno = [
    aPantalla(def.gx - 0.2, def.gy + 1.3),
    aPantalla(def.gx - 0.2, def.gy - 1.2),
    aPantalla(def.gx + ancho + 0.2, def.gy - 1.2),
    aPantalla(def.gx + ancho + 0.2, def.gy + 1.3)
  ];
  seleccion
    .poly(aplanar(contorno))
    .stroke({ width: 2, color: PALETA.textoClaro, alpha: 0.85 });
  seleccion.visible = false;
  nodo.addChild(seleccion);

  /* La zona sensible. Cubre el escritorio y el espacio del personaje: pulsar
     «el puesto» tiene que funcionar también pulsando al lado de la silla, que
     es donde la gente pulsa. */
  nodo.eventMode = 'static';
  nodo.cursor = 'pointer';
  // La silueta de un prisma isométrico es un HEXÁGONO convexo: la cara superior
  // más las dos laterales que miran a la cámara. El primer intento encadenó seis
  // puntos mezclando alturas sin ese orden y salió un polígono que se cruza a sí
  // mismo; el recuento de cruces de un polígono así deja AGUJEROS, y pulsar en
  // medio del puesto no seleccionaba nada. Se vio en el navegador, no acá: es
  // justo el hueco que la escena deja sin cubrir.
  const x0 = def.gx - 0.2;
  const x1 = def.gx + ancho + 0.2;
  const y0 = def.gy - 1.3;
  const y1 = def.gy + 1.3;
  const alto = 2.6;
  nodo.hitArea = new Polygon(
    aplanar([
      aPantalla(x0, y0, alto),
      aPantalla(x1, y0, alto),
      aPantalla(x1, y0, 0),
      aPantalla(x1, y1, 0),
      aPantalla(x0, y1, 0),
      aPantalla(x0, y1, alto)
    ])
  );

  return { def, nodo, ancla, halo, brillos, rotulo, testigo, seleccion, paquete };
}

/* ════════════════════════════════════════════════════════════════════════════
   El montaje del recinto
   ════════════════════════════════════════════════════════════════════════════ */

export function construirOficina(definiciones: DefinicionDePuesto[], texturas: Texturas): Oficina {
  const raiz = new Container();
  raiz.sortableChildren = true;

  const suelo = construirSuelo(MUNDO);
  suelo.zIndex = -2000;
  raiz.addChild(suelo);

  const muros = construirMuros(MUNDO);
  muros.zIndex = -1000;
  raiz.addChild(muros);

  const animables: ((t: number, dt: number) => void)[] = [];

  const mural = construirMural(texturas);
  mural.nodo.zIndex = -900;
  raiz.addChild(mural.nodo);
  animables.push(mural.animar);

  const muebles: Mueble[] = [
    construirArmario(2.4, texturas),
    construirArmario(4.2, texturas),
    construirPanelDeFibra(6.3),
    construirLuminaria(4, 3, texturas),
    construirLuminaria(9, 6, texturas),
    construirPlanta(12.4, 1.1, texturas),
    construirPlanta(0.9, 8.9, texturas),
    construirBanco(11.3, 8.2),
    construirDispensador(13.0, 4.6)
  ];
  for (const m of muebles) {
    raiz.addChild(m.nodo);
    if (m.animar) animables.push(m.animar);
  }

  const puestos = definiciones.map((def) => {
    const p = construirPuesto(def, texturas);
    raiz.addChild(p.nodo);
    return p;
  });

  return {
    raiz,
    mundo: MUNDO,
    puestos,
    animar(t, dt) {
      for (const f of animables) f(t, dt);
    },
    destruir() {
      // `children: true` destruye el árbol completo. Las texturas se destruyen
      // aparte, porque son compartidas y las crea quien monta la escena: que
      // este método se las llevara rompería un segundo montaje en la misma
      // página, y el síntoma sería una escena en negro sin ningún error.
      raiz.destroy({ children: true });
    }
  };
}
