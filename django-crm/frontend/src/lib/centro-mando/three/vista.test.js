import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import {
  ALCANCE, MARGEN_PROPIO, anclasDeSala, aplicarModoDeVista, enLaEsquinaCortada, noTapa,
  salaVisible
} from './vista.js';

/**
 * LOS DOS ARREGLOS QUE NO SE PUDIERON VER, MEDIDOS SIN PANTALLA.
 *
 * El 01/11/2026 se corrigieron dos defectos del spike y quedaron sin verificar
 * porque el motor de Docker se cayó: los rótulos de salas tapadas y la
 * cubierta en «Rayos X». Los dos vivían dentro de `montarThree`, que necesita
 * un `WebGLRenderer`.
 *
 * Three.js es JavaScript puro —`Raycaster`, `Plane`, `Mesh` y el grafo de
 * escena no necesitan WebGL— así que esto corre en Node con la matemática de
 * verdad, no con una maqueta de ella.
 *
 * QUÉ PRUEBA Y QUÉ NO. Prueba que la decisión es correcta: que un rótulo tapado
 * se apaga, que uno al descubierto no, que el recorte se respeta y que la
 * cubierta se apaga en rayos X. **No prueba cómo queda en pantalla**, y eso
 * sigue pendiente de un navegador.
 */

/** La dirección de la cámara del spike, igual que en `escena-three.js`. */
const DIRECCION = new THREE.Vector3(1, 0.88, 1).normalize();

const caja = (ancho, alto, fondo, x, y, z, padre) => {
  const m = new THREE.Mesh(
    new THREE.BoxGeometry(ancho, alto, fondo),
    new THREE.MeshBasicMaterial()
  );
  m.position.set(x + ancho / 2, y + alto / 2, z + fondo / 2);
  padre.add(m);
  m.updateMatrixWorld(true);
  return m;
};

const planosDePrueba = () => [
  new THREE.Plane(new THREE.Vector3(-1, 0, 0), 25),
  new THREE.Plane(new THREE.Vector3(0, 0, -1), 25)
];

describe('el recorte: qué puntos no se dibujan', () => {
  const vista = { modo: 'corte', soloNivel: null, planos: planosDePrueba() };

  it('la esquina que mira a la cámara está cortada', () => {
    expect(enLaEsquinaCortada({ x: 30, z: 30 }, vista)).toBe(true);
  });

  it('y el resto del edificio no', () => {
    expect(enLaEsquinaCortada({ x: 10, z: 30 }, vista)).toBe(false);
    expect(enLaEsquinaCortada({ x: 30, z: 10 }, vista)).toBe(false);
    expect(enLaEsquinaCortada({ x: 10, z: 10 }, vista)).toBe(false);
  });

  it('en sección y en rayos X no hay corte, así que no hay esquina cortada', () => {
    for (const modo of ['seccion', 'rayosX']) {
      expect(enLaEsquinaCortada({ x: 30, z: 30 }, { ...vista, modo })).toBe(false);
    }
  });

  it('y con un piso aislado tampoco: ahí no se recorta nada', () => {
    expect(enLaEsquinaCortada({ x: 30, z: 30 }, { ...vista, soloNivel: 2 })).toBe(false);
  });
});

describe('el rótulo de una sala tapada se apaga, y el de una visible no', () => {
  const nadaSeIgnora = () => false;

  /** Una sala sola, sin nada encima. */
  function salaAlDescubierto() {
    const raiz = new THREE.Group();
    caja(10, 0.4, 8, 0, 0, 0, raiz);   // su suelo
    raiz.updateMatrixWorld(true);
    return { raiz, ancla: new THREE.Vector3(5, 1.5, 4) };
  }

  it('sin nada encima, se ve', () => {
    const { raiz, ancla } = salaAlDescubierto();
    expect(salaVisible(new THREE.Raycaster(), raiz, ancla, DIRECCION, nadaSeIgnora)).toBe(true);
  });

  it('con una cubierta encima, NO se ve', () => {
    //  El defecto exacto que se arregló: el edificio mostraba «NOC y Redes»
    //  escrito sobre la cubierta, nombrando una sala dos plantas más abajo.
    const { raiz, ancla } = salaAlDescubierto();
    caja(60, 0.6, 60, -20, 14, -20, raiz);
    raiz.updateMatrixWorld(true);
    expect(salaVisible(new THREE.Raycaster(), raiz, ancla, DIRECCION, nadaSeIgnora)).toBe(false);
  });

  it('su propio suelo no la tapa a sí misma', () => {
    //  Es el falso positivo que haría que NINGUNA sala se viera nunca, y la
    //  razón de que exista `MARGEN_PROPIO`.
    const { raiz, ancla } = salaAlDescubierto();
    expect(MARGEN_PROPIO).toBeGreaterThan(0);
    expect(salaVisible(new THREE.Raycaster(), raiz, ancla, DIRECCION, nadaSeIgnora)).toBe(true);
  });

  it('EL RECORTE SE RESPETA: una cubierta en la esquina cortada no tapa', () => {
    //  LA PRUEBA QUE IMPORTA. El trazador de rayos no conoce los planos de
    //  recorte: la esquina que el corte se llevó sigue estando para él. Antes
    //  del arreglo, todos los rótulos chocaban con geometría invisible y
    //  desaparecían a la vez.
    const raiz = new THREE.Group();
    caja(10, 0.4, 8, 30, 0, 30, raiz);            // la sala, en la esquina
    const ancla = new THREE.Vector3(35, 1.5, 34);
    caja(60, 0.6, 60, 0, 14, 0, raiz);            // una cubierta por encima
    raiz.updateMatrixWorld(true);

    const vista = { modo: 'corte', soloNivel: null, planos: planosDePrueba() };
    const cortado = (tocado) => noTapa(tocado, vista);

    //  Sin saber del recorte diría que está tapada…
    expect(salaVisible(new THREE.Raycaster(), raiz, ancla, DIRECCION, () => false)).toBe(false);
    //  …y sabiéndolo, se ve, porque lo que la tapaba no se dibuja.
    expect(salaVisible(new THREE.Raycaster(), raiz, ancla, DIRECCION, cortado)).toBe(true);
  });

  it('EL RAYO ES PARALELO: no se parece al que saldría de la cámara', () => {
    //  La otra mitad del mismo defecto. En ortográfica los rayos son
    //  paralelos; uno lanzado desde la posición de la cámara es de
    //  perspectiva, y con el edificio entero en el encuadre los dos contestan
    //  distinto. Esta prueba fija la diferencia: si alguien «simplificara»
    //  `salaVisible` volviendo a usar la cámara, esto se pone en rojo.
    const raiz = new THREE.Group();
    caja(10, 0.4, 8, 0, 0, 0, raiz);
    const ancla = new THREE.Vector3(5, 1.5, 4);
    //  Un obstáculo colocado donde pasa el rayo PARALELO pero no el que
    //  vendría de una cámara puesta muy lejos en otra dirección.
    const enElCamino = ancla.clone().addScaledVector(DIRECCION, 40);
    caja(6, 6, 6, enElCamino.x - 3, enElCamino.y - 3, enElCamino.z - 3, raiz);
    raiz.updateMatrixWorld(true);
    expect(salaVisible(new THREE.Raycaster(), raiz, ancla, DIRECCION, () => false)).toBe(false);

    //  Y el control de la mutación: con el obstáculo fuera del camino
    //  paralelo, la misma sala se ve. Sin esto, un `salaVisible` que
    //  devolviera siempre `false` pasaría la afirmación de arriba.
    const otra = new THREE.Group();
    caja(10, 0.4, 8, 0, 0, 0, otra);
    caja(6, 6, 6, -60, 20, 60, otra);
    otra.updateMatrixWorld(true);
    expect(salaVisible(new THREE.Raycaster(), otra, ancla, DIRECCION, () => false)).toBe(true);
  });

  it('el rayo sale a la distancia declarada y no a ojo', () => {
    expect(ALCANCE).toBeGreaterThan(100);
  });
});

describe('los modos de vista hacen lo que su botón promete', () => {
  /** Un edificio de juguete con lo que `aplicarModoDeVista` necesita. */
  function edificioDeJuguete() {
    const escena = new THREE.Scene();
    const raiz = new THREE.Group();
    escena.add(raiz);
    const porNivel = new Map();
    for (const nivel of [1, 2, 3]) {
      const g = new THREE.Group();
      const losa = caja(40, 0.4, 38, 0, nivel * 7, 0, g);
      g.userData.losa = losa;
      raiz.add(g);
      porNivel.set(nivel, g);
    }
    //  La cubierta: varios hijos de `raiz` marcados, como los marca el spike.
    const cubierta = [];
    for (let i = 0; i < 3; i++) {
      const c = caja(40, 0.5, 38, 0, 28 + i * 0.1, 0, raiz);
      c.userData.esCubierta = true;
      cubierta.push(c);
    }
    escena.updateMatrixWorld(true);
    return { escena, raiz, porNivel, cubierta, planos: planosDePrueba(),
             huella: { ancho: 40, fondo: 38 } };
  }

  it('«Rayos X» APAGA la cubierta, que es el arreglo sin verificar', () => {
    //  El defecto: la cubierta quedaba opaca. El botón respondía, el modo
    //  cambiaba, y en pantalla no pasaba nada.
    const e = edificioDeJuguete();
    aplicarModoDeVista({ ...e, modo: 'rayosX', soloNivel: null });
    expect(e.cubierta.map((c) => c.visible)).toEqual([false, false, false]);
  });

  it('y en los otros dos modos la cubierta está puesta', () => {
    for (const modo of ['corte', 'seccion']) {
      const e = edificioDeJuguete();
      aplicarModoDeVista({ ...e, modo, soloNivel: null });
      expect(e.cubierta.every((c) => c.visible), `cubierta apagada en ${modo}`).toBe(true);
    }
  });

  it('volver de rayos X la enciende otra vez', () => {
    //  Un apagado que no se deshace es el mismo defecto al revés.
    const e = edificioDeJuguete();
    aplicarModoDeVista({ ...e, modo: 'rayosX', soloNivel: null });
    aplicarModoDeVista({ ...e, modo: 'corte', soloNivel: null });
    expect(e.cubierta.every((c) => c.visible)).toBe(true);
  });

  it('en rayos X las losas de arriba se atenúan y la de abajo no', () => {
    const e = edificioDeJuguete();
    aplicarModoDeVista({ ...e, modo: 'rayosX', soloNivel: null });
    expect(e.porNivel.get(1).userData.losa.material.transparent).toBe(false);
    expect(e.porNivel.get(2).userData.losa.material.opacity).toBeLessThan(0.5);
    expect(e.porNivel.get(3).userData.losa.material.opacity).toBeLessThan(0.5);
  });

  it('«Corte» recorta TODOS los materiales, no sólo los muros', () => {
    //  Un muro recortado junto a un escritorio entero deja un escritorio
    //  flotando en el aire.
    const e = edificioDeJuguete();
    aplicarModoDeVista({ ...e, modo: 'corte', soloNivel: null });
    const mallas = [];
    e.escena.traverse((o) => { if (o.isMesh) mallas.push(o); });
    expect(mallas.length).toBeGreaterThan(5);
    for (const m of mallas) {
      expect(m.material.clippingPlanes, 'una malla sin recortar').toHaveLength(2);
      expect(m.material.clipIntersection).toBe(true);
    }
  });

  it('«Sección» y un piso aislado no recortan nada', () => {
    for (const v of [{ modo: 'seccion', soloNivel: null }, { modo: 'corte', soloNivel: 2 }]) {
      const e = edificioDeJuguete();
      aplicarModoDeVista({ ...e, ...v });
      const mallas = [];
      e.escena.traverse((o) => { if (o.isMesh) mallas.push(o); });
      for (const m of mallas) expect(m.material.clippingPlanes).toBeNull();
    }
  });

  it('el corte se coloca sobre la huella real, no sobre un número fijo', () => {
    const e = edificioDeJuguete();
    aplicarModoDeVista({ ...e, huella: { ancho: 100, fondo: 50 }, modo: 'corte', soloNivel: null });
    expect(e.planos[0].constant).toBeCloseTo(62, 1);
    expect(e.planos[1].constant).toBeCloseTo(31, 1);
  });

  it('un edificio sin niveles no rompe el modo', () => {
    const e = edificioDeJuguete();
    expect(() => aplicarModoDeVista({ ...e, porNivel: new Map(), modo: 'rayosX', soloNivel: null }))
      .not.toThrow();
  });
});

describe('lo que el trazador de rayos NO sabe, y hubo que enseñarle', () => {
  const vista = () => ({ modo: 'rayosX', soloNivel: null, planos: planosDePrueba() });
  const choque = (objeto, x = 0, z = 0) => ({ point: { x, z }, object: objeto });

  it('una malla APAGADA no tapa, aunque el rayo choque con ella', () => {
    //  MEDIDO EN EL BANCO, Y ES EL QUE MÁS ENGAÑA. En «Rayos X» la cubierta
    //  se apaga y en pantalla desaparece, pero seguía bloqueando 27 de 40
    //  rayos: el botón funcionaba y el efecto que faltaba estaba en otra
    //  parte. Sin esta regla, los nombres del piso de arriba se perdían justo
    //  en el modo que existe para verlos.
    const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
    m.visible = false;
    expect(noTapa(choque(m), vista())).toBe(true);
    m.visible = true;
    expect(noTapa(choque(m), vista())).toBe(false);
  });

  it('y tampoco tapa si quien está apagado es su grupo', () => {
    //  En Three.js la visibilidad se hereda al dibujar. Mirar sólo la malla
    //  dejaría pasar un piso entero apagado.
    const g = new THREE.Group();
    const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
    g.add(m);
    g.visible = false;
    expect(noTapa(choque(m), vista())).toBe(true);
  });

  it('una losa TRASLÚCIDA no tapa; una opaca sí', () => {
    const traslucida = new THREE.Mesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.18 })
    );
    const opaca = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
    expect(noTapa(choque(traslucida), vista())).toBe(true);
    expect(noTapa(choque(opaca), vista())).toBe(false);
  });

  it('pero una casi opaca sí tapa: el umbral no es «cualquier transparencia»', () => {
    const casi = new THREE.Mesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.9 })
    );
    expect(noTapa(choque(casi), vista())).toBe(false);
  });
});

describe('dónde se ancla el nombre de una sala', () => {
  const sala = { x: 10, y: 5, z: 20, ancho: 14, fondo: 10 };

  it('el primer candidato es la esquina que mira a la cámara', () => {
    //  LO QUE LA PRIMERA CAPTURA DEL BANCO ENSEÑÓ: con el centro como único
    //  anclaje, diez de once rótulos desaparecían — y el rayo tenía razón, el
    //  centro de una sala está bajo la cubierta. La pregunta correcta no es
    //  «¿se ve el centro?» sino «¿se ve algo, y dónde?».
    const [primero] = anclasDeSala(sala);
    expect(primero.x).toBeGreaterThan(sala.x + sala.ancho / 2);
    expect(primero.z).toBeGreaterThan(sala.z + sala.fondo / 2);
  });

  it('el último es el centro, que es lo que había antes', () => {
    const anclas = anclasDeSala(sala);
    const ultimo = anclas[anclas.length - 1];
    expect(ultimo.x).toBeCloseTo(sala.x + sala.ancho / 2, 5);
    expect(ultimo.z).toBeCloseTo(sala.z + sala.fondo / 2, 5);
  });

  it('todos caen DENTRO de la sala y a la altura del tabique', () => {
    for (const a of anclasDeSala(sala)) {
      expect(a.x).toBeGreaterThan(sala.x);
      expect(a.x).toBeLessThan(sala.x + sala.ancho);
      expect(a.z).toBeGreaterThan(sala.z);
      expect(a.z).toBeLessThan(sala.z + sala.fondo);
      expect(a.y).toBe(sala.y);
    }
  });

  it('hay más de uno: con uno solo esto no serviría de nada', () => {
    expect(anclasDeSala(sala).length).toBeGreaterThan(3);
  });

  it('una sala diminuta no produce anclajes fuera de sí misma', () => {
    //  El retiro es fijo; en una sala de 1,2 celdas invertiría los bordes.
    for (const a of anclasDeSala({ x: 0, y: 0, z: 0, ancho: 1.2, fondo: 1.2 })) {
      expect(a.x).toBeGreaterThanOrEqual(0);
      expect(a.x).toBeLessThanOrEqual(1.2);
    }
  });
});
