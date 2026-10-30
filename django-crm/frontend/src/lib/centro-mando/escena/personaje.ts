/**
 * EL PERSONAJE.
 *
 * Una figura sentada, armada con primitivas y articulada por piezas con nombre:
 * silla, piernas, tronco, brazos, manos, cabeza. Recibe una pose —puros
 * números, de `pose.ts`— y la aplica. No decide nada: no sabe qué animación le
 * toca, ni por qué, ni de dónde salió el dato.
 *
 * POR QUÉ UNA FIGURA ARTICULADA Y NO UNA TIRA DE IMÁGENES
 * Una animación por fotogramas pide arte que no existe, y además obliga a
 * decidir de antemano cuántos estados habrá. Articular las piezas y mover sus
 * transformaciones da transiciones continuas entre dos poses cualesquiera
 * —incluidas las que nadie dibujó— y deja el reemplazo abierto: el día que haya
 * ilustración, cada pieza pasa a ser un sprite y `aplicar()` no cambia.
 *
 * LA ORIENTACIÓN, QUE NO ES NEGOCIABLE
 * Mira hacia la cámara, es decir hacia `+gy`. Lo contrario —de espaldas,
 * mirando el mural— sería más fiel a cómo trabaja una sala real, y se descartó:
 * de un personaje de espaldas no se ve ni la cabeza girar ni las manos, y
 * entonces las cinco animaciones se distinguen por nada.
 *
 * LO QUE ESTE ARCHIVO NO PUEDE PROBAR
 * Que las piezas queden donde deben se ve mirando, y no hay cómo probarlo acá:
 * en este repositorio no arranca jsdom. Lo que SÍ está probado es lo que decide
 * las poses (`pose.ts`) y lo que decide qué pose toca (`adaptador.ts`). Este
 * archivo es el único de los tres que se verifica con el navegador, y conviene
 * decirlo en vez de dar a entender que todo está cubierto.
 */

import { Container, Graphics, Sprite, Text } from 'pixi.js';
import { PALETA, aspectoDe, mezclarColor, tono, type Aspecto } from './paleta';
import type { Pose } from './pose';
import type { Texturas } from './texturas';

export interface Personaje {
  nodo: Container;
  /** Aplica una pose. Se llama una vez por fotograma. */
  aplicar(pose: Pose): void;
  destruir(): void;
}

/**
 * Las medidas, en píxeles de mundo y desde el suelo hacia arriba (negativas).
 *
 * Están juntas y con nombre porque son lo que hay que ajustar cuando la figura
 * «no cuadra con el escritorio»: tocar números sueltos repartidos por el
 * archivo es cómo se termina con una cabeza que flota y unas manos que
 * atraviesan la mesa.
 */
const M = {
  asiento: -15,
  hombros: -37,
  cuello: -42,
  cabeza: -49,
  radioCabeza: 7.4,
  /** Dónde están las manos en reposo sobre la mesa, relativo al ancla. */
  manoX: -22,
  manoY: -11
};

/**
 * @param lugar el puesto que ocupa en su sala. Garantiza que dos compañeros no
 *        lleven la misma camisa; ver `aspectoDe`. Se llama `lugar` y no
 *        `asiento` porque acá dentro `asiento` ya es una pieza de la silla, y
 *        el choque no lo vio ninguna prueba: este archivo no lo importa
 *        ninguna, así que un error de sintaxis acá solo aparece en el
 *        navegador.
 * @param quien el nombre del agente. De él sale el aspecto: ropa, pelo y piel.
 *        Estable —el mismo agente se ve igual en dos cargas— y arbitrario: el
 *        reparto no codifica nada y no hay que leerlo. Sin nombre, todos
 *        vuelven a ser la misma persona, que es lo que había antes.
 */
export function construirPersonaje(texturas: Texturas, quien = '', lugar = 0): Personaje {
  const A: Aspecto = quien
    ? aspectoDe(quien, lugar)
    : { camisa: PALETA.camisa, camisaSombra: PALETA.camisaSombra,
        pelo: PALETA.pelo, piel: PALETA.piel };
  const nodo = new Container();

  /* ── sombra de contacto ───────────────────────────────────────────────── */
  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  sombra.width = 52;
  sombra.height = 26;
  sombra.alpha = 0.55;
  nodo.addChild(sombra);

  /* ── la silla, en dos trozos ──────────────────────────────────────────── */
  /* El respaldo va DETRÁS del tronco y la base DELANTE de las piernas, así que
     no puede ser una sola pieza: hay que intercalar el cuerpo entre las dos. */
  const respaldo = new Graphics();
  respaldo
    .roundRect(-9, M.hombros - 6, 19, 26, 5)
    .fill({ color: PALETA.sillaTela })
    .roundRect(-7, M.hombros - 4, 15, 22, 4)
    .fill({ color: tono(PALETA.sillaTela, 0.12) });
  respaldo.x = 5;
  respaldo.y = 2;
  nodo.addChild(respaldo);

  const baseSilla = new Graphics();
  baseSilla
    .ellipse(0, -2, 13, 6)
    .fill({ color: PALETA.sillaBase })
    .rect(-2.5, -13, 5, 11)
    .fill({ color: PALETA.metal });
  nodo.addChild(baseSilla);

  /* ── el cuerpo ────────────────────────────────────────────────────────── */
  /* Todo lo que respira cuelga de este contenedor: subirlo un píxel sube la
     figura entera sin desarmar la silla. */
  const cuerpo = new Container();
  nodo.addChild(cuerpo);

  const asiento = new Graphics();
  asiento.ellipse(0, M.asiento, 12, 5.5).fill({ color: tono(PALETA.sillaTela, 0.08) });
  cuerpo.addChild(asiento);

  // Los muslos salen hacia la cámara (+gy en pantalla es abajo-izquierda).
  const piernas = new Graphics();
  piernas
    .moveTo(-3, M.asiento - 1)
    .lineTo(-17, M.asiento + 6)
    .lineTo(-16, M.asiento + 11)
    .lineTo(-1, M.asiento + 5)
    .fill({ color: PALETA.pantalon })
    .moveTo(4, M.asiento - 1)
    .lineTo(-9, M.asiento + 8)
    .lineTo(-8, M.asiento + 13)
    .lineTo(6, M.asiento + 4)
    .fill({ color: tono(PALETA.pantalon, -0.12) });
  cuerpo.addChild(piernas);

  // El tronco: más estrecho en la cadera que en los hombros. Un rectángulo
  // recto se lee como una caja con cabeza.
  const tronco = new Graphics();
  tronco
    .moveTo(-9, M.asiento)
    .lineTo(-10.5, M.hombros + 4)
    .quadraticCurveTo(-10.5, M.hombros - 2, -5, M.hombros - 2)
    .lineTo(6, M.hombros - 2)
    .quadraticCurveTo(11, M.hombros - 2, 11, M.hombros + 4)
    .lineTo(9, M.asiento)
    .fill({ color: A.camisa });
  // El costado en sombra: la luz entra por el mismo lado que en el mobiliario.
  tronco
    .moveTo(4, M.hombros - 2)
    .lineTo(6, M.hombros - 2)
    .quadraticCurveTo(11, M.hombros - 2, 11, M.hombros + 4)
    .lineTo(9, M.asiento)
    .lineTo(4, M.asiento)
    .fill({ color: A.camisaSombra });
  cuerpo.addChild(tronco);

  /* ── los brazos ───────────────────────────────────────────────────────── */
  /* Cada brazo es un trazo grueso del hombro a la mano, redibujado cuando la
     mano se mueve. Es la única parte que se vuelve a dibujar en cada fotograma,
     y son dos trazos: el coste es irrelevante y el resultado se dobla como un
     brazo en vez de girar como una tabla clavada al hombro. */
  const brazos = new Graphics();
  cuerpo.addChild(brazos);

  const manoIzq = new Graphics();
  manoIzq.circle(0, 0, 3.2).fill({ color: A.piel });
  const manoDer = new Graphics();
  manoDer.circle(0, 0, 3.2).fill({ color: A.piel });
  cuerpo.addChild(manoIzq, manoDer);

  /* ── la cabeza ────────────────────────────────────────────────────────── */
  const cabeza = new Container();
  cabeza.y = M.cabeza;
  cuerpo.addChild(cabeza);

  const cuello = new Graphics();
  cuello.rect(-2.5, -2, 5, M.hombros - M.cuello + 7).fill({ color: tono(A.piel, -0.22) });
  cabeza.addChild(cuello);

  const craneo = new Graphics();
  craneo
    .circle(0, 0, M.radioCabeza)
    .fill({ color: A.piel })
    // El lado en sombra, recortado por el propio círculo: media luna de un
    // tono más bajo. Sin esto la cabeza es un disco.
    .moveTo(2, -M.radioCabeza + 1)
    .arc(0, 0, M.radioCabeza, -1.2, 1.2)
    .fill({ color: tono(A.piel, -0.16) });
  cabeza.addChild(craneo);

  const pelo = new Graphics();
  pelo
    .moveTo(-M.radioCabeza - 0.5, -1)
    .arc(0, -0.5, M.radioCabeza + 0.6, Math.PI, 0)
    .lineTo(M.radioCabeza, -1)
    .quadraticCurveTo(3, -3.5, -M.radioCabeza - 0.5, -1)
    .fill({ color: A.pelo });
  cabeza.addChild(pelo);

  // Los auriculares: lo que dice «esto es un puesto de operación» sin una sola
  // palabra. Arco sobre la cabeza y una almohadilla en la sien visible.
  const auriculares = new Graphics();
  auriculares
    .moveTo(-M.radioCabeza - 1.5, -1)
    .arc(0, -0.5, M.radioCabeza + 1.8, Math.PI, 0)
    .stroke({ width: 1.8, color: PALETA.auricular })
    .roundRect(-M.radioCabeza - 3.4, -2.6, 3.4, 6, 1.6)
    .fill({ color: PALETA.auricular })
    .roundRect(M.radioCabeza - 0.4, -2.6, 3.4, 6, 1.6)
    .fill({ color: PALETA.auricular })
    // La varilla del micrófono, hacia la pantalla.
    .moveTo(-M.radioCabeza - 2, 2)
    .quadraticCurveTo(-M.radioCabeza - 6, 4.5, -M.radioCabeza - 4.5, 6.5)
    .stroke({ width: 1.3, color: PALETA.auricular });
  cabeza.addChild(auriculares);

  // Los ojos: dos puntos. A esta escala es todo lo que cabe, y dos puntos en el
  // sitio correcto son la diferencia entre una persona y un maniquí.
  const cara = new Graphics();
  cara
    .circle(-3.6, 1.2, 0.95)
    .circle(0.6, 1.2, 0.95)
    .fill({ color: A.pelo });
  cabeza.addChild(cara);

  /* ── el signo de interrogación ────────────────────────────────────────── */
  /* No es un adorno: es la marca de que la escena NO SABE qué está haciendo
     este puesto. Va sobre la cabeza y sobre su propia placa, para que se lea
     sobre cualquier fondo. */
  const incertidumbre = new Container();
  const globo = new Graphics();
  globo
    .circle(0, 0, 9)
    .fill({ color: PALETA.placa, alpha: 0.9 })
    .circle(0, 0, 9)
    .stroke({ width: 1.2, color: PALETA.incognito, alpha: 0.9 });
  const signo = new Text({
    text: '?',
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: 13,
      fontWeight: '700',
      fill: PALETA.textoClaro
    },
    resolution: 2
  });
  signo.anchor.set(0.5);
  signo.y = 0.5;
  incertidumbre.addChild(globo, signo);
  // A un lado de la cabeza, no encima: la placa con el nombre del puesto vive
  // justo ahí arriba y se lo comía entero. Medido con una captura — el estado
  // decía «no sé» y el signo no aparecía por ninguna parte.
  incertidumbre.x = 21;
  incertidumbre.y = M.cabeza - 13;
  incertidumbre.visible = false;
  nodo.addChild(incertidumbre);

  /* ── aplicación de la pose ────────────────────────────────────────────── */

  /**
   * Las figuras que se tiñen. Se enumeran una vez, acá, y no se buscan en el
   * árbol: recorrer los hijos funcionaría hoy y se saltaría la primera pieza
   * nueva que alguien meta dentro de otro grupo.
   */
  const tintables: Graphics[] = [
    respaldo, baseSilla, asiento, piernas, tronco, brazos,
    manoIzq, manoDer, cuello, craneo, pelo, auriculares, cara
  ];

  let ultimoApagado = -1;

  function aplicar(pose: Pose) {
    cuerpo.y = pose.torsoY;
    // Inclinarse hacia el equipo se consigue cizallando el tronco, no
    // rotándolo: rotar le despega la cadera del asiento.
    tronco.skew.x = -pose.torsoInclina;
    piernas.skew.x = -pose.torsoInclina * 0.25;

    cabeza.x = pose.cabezaGiro;
    cabeza.y = M.cabeza + pose.cabezaY - pose.torsoInclina * 6;
    cabeza.rotation = pose.cabezaInclina * 0.35;
    // La cara y el pelo acompañan el giro un poco más que el cráneo: es lo que
    // da la sensación de que la cabeza gira y no de que se desplaza.
    cara.x = pose.cabezaGiro * 0.45;
    pelo.x = pose.cabezaGiro * 0.12;

    const mix = pose.alcance;
    manoIzq.position.set(M.manoX + 6, M.manoY + pose.manoIzqY);
    manoDer.position.set(M.manoX - 7 - mix, M.manoY + pose.manoDerY - mix * 0.5);

    brazos.clear();
    brazos
      .moveTo(-7, M.hombros + 2)
      .quadraticCurveTo(-15, M.hombros + 12, manoIzq.x, manoIzq.y)
      .stroke({ width: 5.2, color: A.camisa, cap: 'round' })
      .moveTo(2, M.hombros + 2)
      .quadraticCurveTo(-8, M.hombros + 14, manoDer.x, manoDer.y)
      .stroke({ width: 5.2, color: A.camisaSombra, cap: 'round' });

    incertidumbre.visible = pose.incertidumbre > 0.02;
    if (incertidumbre.visible) {
      incertidumbre.alpha = Math.min(1, pose.incertidumbre);
      incertidumbre.y = M.cabeza - 13 - pose.incertidumbre * 3;
      incertidumbre.scale.set(0.9 + pose.incertidumbre * 0.12);
    }

    // EL APAGADO VA FIGURA POR FIGURA, no al contenedor.
    //
    // La primera versión hacía `cuerpo.tint = ...` sobre el `Container` que
    // agrupa tronco, cabeza y brazos. **En PixiJS 8 un `Container` no tiene
    // `tint`**: la propiedad existe en las figuras (`Graphics`, `Sprite`), no
    // en el grupo. Asignarla no falla, no avisa y no hace nada — el personaje
    // seguía con su color en «no sé» y la pantalla volvía a decir que todo
    // estaba normal, que es exactamente la mentira que este estado existe para
    // romper. Se vio comparando los píxeles del lienzo, no mirando: a simple
    // vista la diferencia entre «apagado» y «no apagado» era creíble.
    //
    // Solo cuando cambia: escribir `tint` en cada fotograma invalida el lote de
    // dibujo de cada figura.
    if (Math.abs(pose.apagado - ultimoApagado) > 0.01) {
      ultimoApagado = pose.apagado;
      const tinte = mezclarColor(0xffffff, 0x6e6c86, pose.apagado);
      for (const pieza of tintables) pieza.tint = tinte;
      cuerpo.alpha = 1 - pose.apagado * 0.45;
    }
  }

  aplicar({
    torsoY: 0,
    torsoInclina: 0,
    cabezaY: 0,
    cabezaGiro: 0,
    cabezaInclina: 0,
    manoIzqY: 0,
    manoDerY: 0,
    alcance: 0,
    brilloPantalla: 0.6,
    aura: 0,
    apagado: 0,
    incertidumbre: 0,
    despacho: 0
  });

  return {
    nodo,
    aplicar,
    destruir() {
      nodo.destroy({ children: true });
    }
  };
}
