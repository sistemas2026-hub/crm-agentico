/**
 * LA PROYECCIÓN ISOMÉTRICA, Y NADA MÁS.
 *
 * Convierte una celda de la rejilla (gx, gy, gz) en un punto de pantalla. Es
 * aritmética pura: no importa PixiJS, no toca el DOM y por eso se puede probar
 * en Node, que es donde se prueba todo lo demás de este repositorio.
 *
 * LA LECCIÓN QUE ESTE ARCHIVO GUARDA
 * El plano isométrico anterior (el SVG de `planta.js`) se dibujó tres veces mal
 * por el mismo motivo: la matriz de un muro recorrido de adelante hacia atrás
 * tiene determinante negativo y **el texto sale espejado**. Acá no hay matrices
 * —se proyecta punto por punto— justamente para que ese error no pueda volver:
 * un polígono mal orientado se ve, pero un texto espejado dentro de una pared
 * oscura no, y se descubre en una captura tres días después.
 *
 * LA RELACIÓN 2:1
 * `ancho = 2 × alto` es la isometría clásica de videojuego: las diagonales caen
 * exactamente a 1 píxel por cada 2 horizontales, así que un borde recto no
 * tiene escalones irregulares. Cualquier otra relación obliga a antialias para
 * tapar el serrucho, y el antialias sobre líneas de 1 px borronea toda la
 * escena.
 */

/** Medidas de una baldosa del suelo, en píxeles de mundo (sin zoom). */
export const BALDOSA = { ancho: 64, alto: 32 } as const;

/** Cuánto sube en pantalla una unidad de altura. */
export const ALTURA_UNIDAD = 26;

/** @see aPantalla */
export interface Punto {
  x: number;
  y: number;
}

/**
 * Celda de rejilla → punto de pantalla, en el espacio del mundo.
 *
 * El origen (0,0,0) es la esquina más lejana del suelo. La `y` de pantalla
 * CRECE hacia abajo, así que la altura se RESTA: un objeto alto se dibuja más
 * arriba. Olvidar ese signo hunde el mobiliario dentro del piso, que es el
 * primer síntoma que aparece cuando alguien «mejora» esta función.
 */
export function aPantalla(gx: number, gy: number, gz = 0): Punto {
  return {
    x: (gx - gy) * (BALDOSA.ancho / 2),
    y: (gx + gy) * (BALDOSA.alto / 2) - gz * ALTURA_UNIDAD
  };
}

/**
 * El orden de pintado: quien tiene menos profundidad se dibuja primero.
 *
 * `gx + gy` es la distancia a la cámara en isometría. Dos objetos con la misma
 * profundidad se solapan de forma indefinida, y ahí es donde aparece el
 * parpadeo entre fotogramas; por eso el desempate es explícito y lo decide
 * quien monta la escena, no el azar del orden de creación.
 */
export function profundidad(gx: number, gy: number, gz = 0): number {
  return gx + gy + gz * 0.001;
}

/**
 * Punto de pantalla → celda de rejilla. Es la inversa exacta de `aPantalla`
 * a altura cero.
 *
 * Existe para saber sobre qué baldosa está el puntero sin consultarle a la
 * escena. Que la ida y la vuelta cierren es una propiedad comprobable, y está
 * comprobada: sin eso, un día el puntero selecciona la celda de al lado y nadie
 * sabe si el error está en la proyección o en la cámara.
 */
export function aRejilla(x: number, y: number): Punto {
  const mx = x / (BALDOSA.ancho / 2);
  const my = y / (BALDOSA.alto / 2);
  return { x: (my + mx) / 2, y: (my - mx) / 2 };
}

/** El tamaño del recinto, en celdas. */
export interface Mundo {
  ancho: number;
  fondo: number;
  alto: number;
  /**
   * El vano de la puerta en el muro de FONDO (`gy = 0`), en celdas `gx`.
   *
   * Decía «muro lateral (`gx = 0`), en celdas `gy`» y era falso: `oficina.ts`
   * la pinta con `panelMuroFondo` recorriendo `gx`. Nadie lo notó porque el
   * único que la usaba —`edificio.js`— pone su circulación justo al fondo, así
   * que el resultado era correcto por el muro equivocado.
   *
   * Lo pone el compositor del edificio y NO la plantilla: una sala no sabe si
   * da a un pasillo. Mirada sola no lleva puerta, y es correcto — un hueco que
   * no da a ningún sitio es un agujero, no una puerta.
   */
  puerta?: [number, number];

  /**
   * El vano en el muro LATERAL (`gx = 0`), en celdas `gy`.
   *
   * Hace falta porque una sala solo tiene dos muros —el de fondo y el
   * lateral— y los otros dos lados están abiertos hacia la cámara. En la sede
   * de una planta eso deja sin entrada a toda una manzana: sus salas tienen la
   * circulación contra el muro lateral, no contra un lado abierto. Medido
   * sobre el piloto: 5 de 11 salas sin forma de entrar.
   */
  puertaLateral?: [number, number];

  /**
   * Qué lados que miran a la cámara llevan peto de cerramiento.
   *
   * `frente` es el borde `gy = fondo` y `derecha` el borde `gx = ancho`: los
   * dos lados que una sala deja abiertos porque un muro entero ahí taparía
   * media sala. El peto los cierra sin tapar a nadie. Ver
   * `construirCerramiento`.
   */
  antepecho?: { frente?: boolean; derecha?: boolean };

  /** El vano de la puerta en el peto del frente, en celdas `gx`. */
  puertaFrente?: [number, number];

  /** El vano de la puerta en el peto de la derecha, en celdas `gy`. */
  puertaDerecha?: [number, number];

  /**
   * Cuanto se cierra esta sala: `restringido`, `estandar` o `semipublico`.
   *
   * Sale de la PLANTILLA y no del departamento: que una sala de expedientes
   * sea privada es una propiedad del tipo de sala, igual que tener
   * estanterias. Asi cualquier empresa que elija esa plantilla recibe el
   * cerramiento que le corresponde sin configurar nada.
   *
   * Decide si la puerta lleva hoja y si lleva lector de acceso. El lector es
   * un DIBUJO: quien puede entrar lo decide el backend, y esta pantalla no
   * lo sabe ni puede saberlo.
   */
  privacidad?: 'restringido' | 'estandar' | 'semipublico';
}

/** Una caja ocupada de verdad: dónde empieza y cuánto mide. */
export interface Volumen {
  origen: { gx: number; gy: number; gz?: number };
  mundo: { ancho: number; fondo: number; alto: number };
}

/**
 * El rectángulo de pantalla que ocupan VARIOS volúmenes.
 *
 * EL DEFECTO QUE ESTO ARREGLA, medido el 31/10/2026: la cámara encuadraba el
 * **cubo** que envuelve al edificio —de (0,0,0) a (ancho, fondo, alto)— y un
 * edificio de tres niveles escalonados no llena ese cubo ni de lejos. La
 * esquina (0, 0, alto) es aire: a treinta y cuatro unidades de altura, sobre
 * el fondo del nivel más bajo, no hay nada. Esa esquina vacía estiraba la caja
 * 884 píxeles hacia arriba, el encuadre ajustaba por ALTO, y el edificio
 * quedaba ocupando el 40% del ancho de la pantalla con un vacío a cada lado.
 *
 * Esto mide lo que de verdad hay: cada planta con su origen y su tamaño. Una
 * planta corta en el piso de arriba deja de inflar la caja.
 *
 * `extensionDelMundo` sigue existiendo para una sala sola, donde el recinto SÍ
 * es un cubo lleno.
 */
export function extensionDeVolumenes(volumenes: Volumen[]) {
  const esquinas: Punto[] = [];
  for (const v of volumenes) {
    const ox = v.origen.gx;
    const oy = v.origen.gy;
    const oz = v.origen.gz ?? 0;
    const { ancho, fondo, alto } = v.mundo;
    //  Las ocho esquinas de la caja. Se podrían deducir las cuatro extremas a
    //  mano —mínimo de x en (0, fondo), máximo en (ancho, 0)…— y es justo el
    //  atajo que se equivoca cuando alguien cambia el signo de la proyección.
    for (const gx of [ox, ox + ancho]) {
      for (const gy of [oy, oy + fondo]) {
        for (const gz of [oz, oz + alto]) esquinas.push(aPantalla(gx, gy, gz));
      }
    }
  }
  if (esquinas.length === 0) {
    return { minX: 0, maxX: 0, minY: 0, maxY: 0, ancho: 0, alto: 0, centro: { x: 0, y: 0 } };
  }
  const xs = esquinas.map((p) => p.x);
  const ys = esquinas.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return {
    minX,
    maxX,
    minY,
    maxY,
    ancho: maxX - minX,
    alto: maxY - minY,
    centro: { x: (minX + maxX) / 2, y: (minY + maxY) / 2 }
  };
}

/**
 * El rectángulo de pantalla que ocupa un mundo completo, incluida la altura de
 * las paredes.
 *
 * La cámara lo necesita para dos cosas: encuadrar al entrar y no dejar que el
 * arrastre saque el recinto de la vista. Calcularlo a ojo —«más o menos el
 * ancho por 64»— deja márgenes asimétricos que se notan al hacer zoom, no al
 * escribir el código.
 */
export function extensionDelMundo(mundo: Mundo) {
  const esquinas = [
    aPantalla(0, 0, mundo.alto),
    aPantalla(mundo.ancho, 0, mundo.alto),
    aPantalla(0, mundo.fondo, mundo.alto),
    aPantalla(mundo.ancho, mundo.fondo, 0),
    aPantalla(0, 0, 0),
    aPantalla(mundo.ancho, mundo.fondo, mundo.alto)
  ];
  const xs = esquinas.map((p) => p.x);
  const ys = esquinas.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return {
    minX,
    maxX,
    minY,
    maxY,
    ancho: maxX - minX,
    alto: maxY - minY,
    centro: { x: (minX + maxX) / 2, y: (minY + maxY) / 2 }
  };
}

/**
 * Los cuatro vértices de una baldosa, en orden antihorario desde el oeste.
 *
 * Devolver el rombo ya armado y no cuatro llamadas sueltas evita el error de
 * cerrar el polígono con tres puntos: el cuarto se olvida, el rombo se ve como
 * un triángulo y parece un problema de la textura.
 */
export function rombo(gx: number, gy: number, gz = 0): Punto[] {
  return [
    aPantalla(gx, gy + 1, gz),
    aPantalla(gx, gy, gz),
    aPantalla(gx + 1, gy, gz),
    aPantalla(gx + 1, gy + 1, gz)
  ];
}
