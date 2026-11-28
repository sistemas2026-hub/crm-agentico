import { describe, it, expect } from 'vitest';
import {
  Camara,
  GESTO,
  LIMITES,
  conSueloQueDejaVerTodo,
  acotarCentro,
  acotarEscala,
  escalaDeEncuadre,
  escalaTrasRueda,
  gesto,
  suavizar
} from './camara';
import { extensionDelMundo } from './isometria';

/**
 * LO QUE MÁS IMPORTA DE ESTE ARCHIVO ES `gesto()`.
 *
 * En el plano anterior, `setPointerCapture` se robaba el clic y pulsar un puesto
 * no hacía nada. Se descubrió a mano, con el navegador, porque acá no hay
 * pruebas de interacción. La causa de fondo era que nadie había decidido qué
 * separa un clic de un arrastre; ahora es una función con números y se puede
 * probar sin DOM.
 */

const ext = extensionDelMundo({ ancho: 14, fondo: 10, alto: 4 });
const vista = { ancho: 1000, alto: 620 };

describe('clic contra arrastre', () => {
  it('pulsar y soltar en el mismo sitio es un clic', () => {
    expect(gesto({ x: 100, y: 100, t: 0 }, { x: 100, y: 100, t: 60 })).toBe('clic');
  });

  it('el temblor normal del pulso sigue siendo un clic', () => {
    // Un clic con el pulso normal mueve el puntero 2-4 px. Si eso contara como
    // arrastre, pulsar un puesto no haría nada la mitad de las veces.
    expect(gesto({ x: 100, y: 100, t: 0 }, { x: 103, y: 98, t: 90 })).toBe('clic');
  });

  it('pasado el radio es un arrastre', () => {
    expect(gesto({ x: 100, y: 100, t: 0 }, { x: 100 + GESTO.radioClic + 1, y: 100, t: 50 })).toBe(
      'arrastre'
    );
  });

  it('mantener pulsado quieto y soltar NO es un clic', () => {
    // El caso raro que sin el umbral de tiempo abriría una ficha un segundo y
    // medio después de que alguien dejara el ratón apoyado.
    expect(gesto({ x: 100, y: 100, t: 0 }, { x: 101, y: 101, t: GESTO.msClic + 10 })).toBe('arrastre');
  });

  it('los umbrales se pueden ajustar', () => {
    expect(gesto({ x: 0, y: 0, t: 0 }, { x: 4, y: 0, t: 10 }, { radioClic: 2, msClic: 350 })).toBe(
      'arrastre'
    );
  });
});

describe('la escala', () => {
  it('nunca sale de los límites', () => {
    expect(acotarEscala(99)).toBe(LIMITES.escalaMax);
    expect(acotarEscala(0.001)).toBe(LIMITES.escalaMin);
    expect(acotarEscala(NaN)).toBe(1);
  });

  it('el zoom es multiplicativo, no aditivo', () => {
    // Con un paso fijo, acercarse desde lejos es lentísimo y desde cerca
    // brutal. Multiplicando, el recorrido percibido es el mismo en todo el
    // rango: la razón entre dos muescas se conserva.
    const a = escalaTrasRueda(0.6, -100);
    const b = escalaTrasRueda(1.2, -100);
    expect(a / 0.6).toBeCloseTo(b / 1.2, 6);
  });

  it('rueda arriba acerca y rueda abajo aleja', () => {
    expect(escalaTrasRueda(1, -100)).toBeGreaterThan(1);
    expect(escalaTrasRueda(1, 100)).toBeLessThan(1);
  });

  it('el encuadre deja el recinto completo dentro de la vista', () => {
    const escala = escalaDeEncuadre(ext, vista);
    expect(ext.ancho * escala).toBeLessThanOrEqual(vista.ancho);
    expect(ext.alto * escala).toBeLessThanOrEqual(vista.alto);
  });

  it('con una vista sin medir todavía, no explota', () => {
    // Al montar, el contenedor puede no estar maquetado: 0 × 0.
    expect(escalaDeEncuadre(ext, { ancho: 0, alto: 0 })).toBe(1);
  });
});

describe('el recinto no se escapa de la vista', () => {
  it('un arrastre enorme no deja la pantalla en negro', () => {
    // Sin el acotado, dos arrastres largos dejan la escena vacía y el único
    // remedio es recargar: no se ve nada que sirva de referencia para volver.
    const centro = acotarCentro({ x: 99999, y: -99999 }, 1.8, ext, vista);
    expect(centro.x).toBeLessThan(ext.maxX + LIMITES.margen);
    expect(centro.y).toBeGreaterThan(ext.minY - LIMITES.margen);
  });

  it('si el recinto cabe de sobra TAMBIEN se puede arrastrar', () => {
    //  Antes esta prueba afirmaba lo contrario —que el centro volvia a
    //  `ext.centro`— y esa era la causa de que el mapa no se dejara mover:
    //  con el plano entero a la vista, arrastrar no hacia nada.
    const vistaGrande = { ancho: 4000, alto: 4000 };
    const quieto = acotarCentro(ext.centro, 0.1, ext, vistaGrande);
    const movido = acotarCentro({ x: ext.centro.x + 300, y: ext.centro.y }, 0.1, ext, vistaGrande);
    expect(movido.x).not.toBeCloseTo(quieto.x, 6);
  });

  it('y aun asi el recinto nunca se sale de la vista', () => {
    //  LA AFIRMACION QUE IMPORTA, y la que la version vieja protegia a costa
    //  de no dejar mover nada: por lejos que se arrastre, el recinto sigue
    //  dentro de la vista. Se comprueba sobre el resultado, no sobre la
    //  entrada, que es lo unico que dice si el acotado sirvio.
    const vistaGrande = { ancho: 4000, alto: 4000 };
    const medioAncho = vistaGrande.ancho / (2 * 0.1);
    const lejos = acotarCentro({ x: 9e6, y: 0 }, 0.1, ext, vistaGrande);
    //  El borde izquierdo de la vista queda a la izquierda del recinto.
    expect(lejos.x - medioAncho).toBeLessThanOrEqual(ext.minX);
    //  Y el derecho, a su derecha.
    expect(lejos.x + medioAncho).toBeGreaterThanOrEqual(ext.maxX);
  });
});

describe('el suavizado no depende de los fotogramas', () => {
  it('el mismo tiempo da el mismo resultado con pasos distintos', () => {
    // Con un factor fijo por fotograma, lo mismo parece suave a 60 fps y se
    // arrastra a 30. Medirlo en una sola máquina es cómo ese error sobrevive.
    let a = 0;
    for (let i = 0; i < 60; i++) a = suavizar(a, 100, 1 / 60);
    let b = 0;
    for (let i = 0; i < 15; i++) b = suavizar(b, 100, 1 / 15);
    expect(Math.abs(a - b)).toBeLessThan(1.5);
  });

  it('converge al destino y no lo pasa', () => {
    let v = 0;
    for (let i = 0; i < 200; i++) v = suavizar(v, 50, 1 / 60);
    expect(v).toBeCloseTo(50, 3);
    expect(v).toBeLessThanOrEqual(50);
  });
});

describe('la cámara', () => {
  it('nace encuadrando el recinto', () => {
    const c = new Camara(ext, vista);
    const e = c.estado();
    expect(e.actual.escala).toBeCloseTo(escalaDeEncuadre(ext, vista), 6);
    expect(e.actual.x).toBeCloseTo(ext.centro.x, 6);
  });

  it('el zoom con la rueda queda anclado al puntero', () => {
    // Sin ancla, acercarse mueve el punto de interés fuera de la pantalla y hay
    // que recolocar con el arrastre después de cada muesca.
    const c = new Camara(ext, vista);
    const puntero = { x: 300, y: 200 };
    const antes = c.estado().destino;
    const mundoAntes = {
      x: antes.x + (puntero.x - vista.ancho / 2) / antes.escala,
      y: antes.y + (puntero.y - vista.alto / 2) / antes.escala
    };
    c.rueda(-240, puntero);
    const despues = c.estado().destino;
    const mundoDespues = {
      x: despues.x + (puntero.x - vista.ancho / 2) / despues.escala,
      y: despues.y + (puntero.y - vista.alto / 2) / despues.escala
    };
    expect(despues.escala).toBeGreaterThan(antes.escala);
    expect(mundoDespues.x).toBeCloseTo(mundoAntes.x, 3);
    expect(mundoDespues.y).toBeCloseTo(mundoAntes.y, 3);
  });

  it('el arrastre se mide en pantalla, no en mundo', () => {
    // Si no se dividiera por la escala, arrastrar con el zoom al máximo
    // lanzaría la escena al infinito.
    const c = new Camara(ext, { ancho: 400, alto: 300 });
    c.rueda(-600, { x: 200, y: 150 });
    const antes = c.estado().destino;
    c.arrastrar(40, 0);
    const corrido = antes.x - c.estado().destino.x;
    expect(corrido).toBeCloseTo(40 / antes.escala, 4);
  });

  it('avanzar acerca lo dibujado a lo pedido', () => {
    const c = new Camara(ext, vista);
    c.arrastrar(-200, -120);
    const destino = c.estado().destino;
    for (let i = 0; i < 90; i++) c.avanzar(1 / 60);
    const actual = c.estado().actual;
    expect(actual.x).toBeCloseTo(destino.x, 1);
    expect(actual.y).toBeCloseTo(destino.y, 1);
  });

  it('la transformación centra lo que la cámara mira', () => {
    const c = new Camara(ext, vista);
    for (let i = 0; i < 120; i++) c.avanzar(1 / 60);
    const tr = c.transformacion();
    const a = c.estado().actual;
    expect(a.x * tr.escala + tr.x).toBeCloseTo(vista.ancho / 2, 4);
    expect(a.y * tr.escala + tr.y).toBeCloseTo(vista.alto / 2, 4);
  });
});

describe('EL SUELO DEL ZOOM NO PUEDE IMPEDIR VER EL CONJUNTO', () => {
  //  EL DEFECTO, medido en el navegador el 31/10/2026: al aislar el piso de
  //  cinco salas el encuadre necesitaba bajar del suelo de zoom, `acotarEscala`
  //  lo subía, el núcleo quedaba cortado por arriba y pulsar «Encuadrar» no
  //  cambiaba NADA — la cámara ya estaba donde podía. Un botón que no hace nada
  //  es peor que no tenerlo: quien lo pulsa cree que eso es todo lo que hay.

  /** Un recinto que NO cabe a la escala mínima por defecto. */
  const enorme = {
    minX: 0, maxX: 12000, minY: 0, maxY: 4000,
    ancho: 12000, alto: 4000, centro: { x: 6000, y: 2000 }
  };
  const vista = { ancho: 1365, alto: 690 };

  it('se afloja sólo cuando hace falta, y lo justo', () => {
    const aflojado = conSueloQueDejaVerTodo(enorme, vista);
    expect(aflojado.escalaMin).toBeLessThan(LIMITES.escalaMin);
    //  Y es EXACTAMENTE la que hace falta: aflojarlo de más deja alejarse
    //  hasta que la escena es un punto.
    expect(aflojado.escalaMin)
      .toBeCloseTo((vista.ancho * 0.9) / enorme.ancho, 6);
  });

  it('y no se toca cuando lo que se mira sí cabe', () => {
    const chico = {
      minX: 0, maxX: 900, minY: 0, maxY: 500,
      ancho: 900, alto: 500, centro: { x: 450, y: 250 }
    };
    expect(conSueloQueDejaVerTodo(chico, vista).escalaMin).toBe(LIMITES.escalaMin);
  });

  it('EL EFECTO: la cámara encuadra el conjunto entero, no un trozo', () => {
    //  La afirmación que de verdad importa, y es sobre el EFECTO: lo que la
    //  cámara abarca a su escala tiene que cubrir el recinto completo. Afirmar
    //  que `escalaMin` bajó no prueba que algo se vea.
    const camara = new Camara(enorme, vista);
    const { escala } = camara.estado().actual;
    expect(vista.ancho / escala).toBeGreaterThanOrEqual(enorme.ancho);
    expect(vista.alto / escala).toBeGreaterThanOrEqual(enorme.alto);
  });
});
