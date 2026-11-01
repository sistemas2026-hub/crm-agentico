/**
 * LO QUE SE VE Y LO QUE NO, separado del montaje para poder probarlo.
 *
 * Por qué existe este archivo
 * ---------------------------
 * Dos defectos del spike se arreglaron el 01/11/2026 y quedaron **sin
 * verificar**, porque el motor de Docker se cayó antes de poder abrir un
 * navegador: los rótulos de salas tapadas y la cubierta en «Rayos X». Los dos
 * vivían dentro de `montarThree`, que necesita un lienzo y un `WebGLRenderer`,
 * así que no había forma de medirlos sin pantalla.
 *
 * Three.js es JavaScript puro: `Raycaster`, `Plane`, `Mesh` y el grafo de
 * escena funcionan en Node sin WebGL. Moviendo estas tres funciones acá, lo
 * que decide la visibilidad **se mide con la matemática de verdad**, en
 * `vista.test.js`, y lo único que sigue sin verificar es cómo queda en
 * pantalla. No es lo mismo que mirarlo, y no se presenta como si lo fuera.
 *
 * Es el mismo corte que `pose.ts` hizo en el prototipo de PixiJS: la decisión
 * en números de un lado, el dibujo del otro.
 */

/**
 * ¿Cae este punto en la esquina que el corte se llevó?
 *
 * Importa porque **el trazador de rayos no conoce los planos de recorte**. La
 * esquina que el corte quita sigue estando ahí para él, así que un rayo choca
 * con geometría que no se dibuja. Ese fue el defecto que ocultó TODOS los
 * rótulos a la vez, y por eso esta pregunta existe aparte.
 *
 * @param {{x: number, z: number}} punto
 * @param {{modo: string, soloNivel: number|null, planos: {constant: number}[]}} vista
 */
export function enLaEsquinaCortada(punto, vista) {
  return (
    vista.modo === 'corte' &&
    vista.soloNivel === null &&
    punto.x > vista.planos[0].constant &&
    punto.z > vista.planos[1].constant
  );
}

/**
 * ¿Este choque NO tapa nada, y hay que seguir de largo?
 *
 * Dos motivos, y los dos son lo mismo: **el trazador de rayos sólo conoce la
 * geometría.** No sabe de planos de recorte ni de transparencia, así que choca
 * con cosas que en pantalla no esconden nada.
 *
 *   1. La esquina que el corte se llevó. Costó que TODOS los rótulos
 *      desaparecieran a la vez.
 *   2. **Un objeto APAGADO.** `visible = false` saca una malla del dibujo y no
 *      del trazado: en «Rayos X» la cubierta se apaga, y aun así era ella la
 *      que bloqueaba 27 de 40 rayos. Medido en el banco el 01/11/2026, con el
 *      techo ya quitado en pantalla y los nombres igual de ausentes.
 *   3. Una losa traslúcida, por lo mismo: se ve a través y el rayo choca.
 *
 * El 2 es el que más engaña, porque el botón funciona —el techo se va— y el
 * efecto que falta está en otra parte.
 *
 * @param {{point: any, object: any}} tocado
 * @param {{modo: string, soloNivel: number|null, planos: {constant: number}[]}} vista
 */
export function noTapa(tocado, vista) {
  if (enLaEsquinaCortada(tocado.point, vista)) return true;
  //  Apagado él o cualquiera de sus padres: en Three.js la visibilidad se
  //  hereda al dibujar, así que mirar sólo la malla deja pasar un grupo entero
  //  apagado.
  for (let o = tocado.object; o; o = o.parent) {
    if (o.visible === false) return true;
  }
  const m = tocado.object?.material;
  const materiales = Array.isArray(m) ? m : [m];
  //  `every`, no `some`: una malla con una cara opaca sí tapa.
  return materiales.length > 0 &&
    materiales.every((x) => x && x.transparent === true && x.opacity < 0.5);
}

/** Desde dónde se lanza el rayo, por detrás del ancla. */
export const ALCANCE = 500;
/**
 * El margen que se le perdona a la propia sala.
 *
 * El suelo de la sala está justo debajo del ancla del rótulo y el rayo lo
 * tocaría a sí mismo. Sin este margen, ninguna sala se ve nunca.
 */
export const MARGEN_PROPIO = 2.6;

/**
 * ¿Se ve esta sala, o hay algo delante?
 *
 * EN CÁMARA ORTOGRÁFICA LOS RAYOS SON PARALELOS. Lanzarlo desde la posición de
 * la cámara hacia el ancla es un rayo de perspectiva, que no es el que dibuja
 * la pantalla: con el edificio entero en el encuadre, los dos difieren lo
 * suficiente para contestar distinto. El rayo correcto sale de detrás del ancla
 * y va en la dirección de la cámara, y por eso esta función **no recibe la
 * cámara**: recibirla sería volver a tener la posibilidad de usarla.
 *
 * @param {any} rayo un `THREE.Raycaster`
 * @param {any} raiz el grafo contra el que se cruza
 * @param {any} mundo el ancla de la sala, en coordenadas del mundo
 * @param {any} direccion la dirección de la cámara, normalizada
 * @param {(tocado: any) => boolean} seIgnora qué choques no esconden nada
 * @returns {boolean}
 */
export function salaVisible(rayo, raiz, mundo, direccion, seIgnora) {
  const origen = mundo.clone().addScaledVector(direccion, ALCANCE);
  rayo.set(origen, direccion.clone().negate());
  for (const tocado of rayo.intersectObject(raiz, true)) {
    if (seIgnora(tocado)) continue;
    return tocado.distance > ALCANCE - MARGEN_PROPIO;
  }
  //  Nada en el camino: se ve. Es el caso de una sala en el borde, y el valor
  //  por omisión tiene que ser «se ve»: esconder un rótulo que sí se podía
  //  leer es peor que mostrar uno de más.
  return true;
}

/**
 * Los puntos donde se puede anclar el rótulo de una sala, del más expuesto al
 * más escondido.
 *
 * POR QUÉ NO ALCANZA CON EL CENTRO, y es lo que la primera captura del banco
 * enseñó: anclado al centro, **diez de once rótulos desaparecían**. Y el
 * trazador de rayos tenía razón — el centro de una sala está bajo la cubierta,
 * así que un rótulo ahí se dibujaría sobre el techo, que es justo el defecto
 * que se quería arreglar—. La prueba era correcta y la pregunta estaba mal: no
 * es «¿se ve el centro?» sino «¿se ve ALGO de esta sala, y dónde?».
 *
 * El orden sale de la cámara: mira desde +x, +y, +z, así que la esquina de
 * mayor `x` y mayor `z` es la que está al frente, y el centro es el último
 * recurso. Un rótulo que nombra una sala invisible desinforma; uno anclado a
 * la parte de la sala que SÍ se ve, informa.
 *
 * @param {{x: number, y: number, z: number, ancho: number, fondo: number}} sala
 * @param {number} [retiro] cuánto se mete hacia adentro del muro
 */
export function anclasDeSala(sala, retiro = 0.8) {
  const x0 = sala.x + retiro;
  const x1 = sala.x + sala.ancho - retiro;
  const z0 = sala.z + retiro;
  const z1 = sala.z + sala.fondo - retiro;
  const cx = sala.x + sala.ancho / 2;
  const cz = sala.z + sala.fondo / 2;
  return [
    { x: x1, y: sala.y, z: z1 },   // la esquina que mira a la cámara
    { x: x1, y: sala.y, z: cz },   // el centro de la cara de mayor x
    { x: cx, y: sala.y, z: z1 },   // el centro de la cara de mayor z
    { x: x1, y: sala.y, z: z0 },
    { x: x0, y: sala.y, z: z1 },
    { x: cx, y: sala.y, z: cz }    // el centro, que es lo que había antes
  ];
}

/**
 * Aplica un modo de vista al grafo: qué se apaga, qué se recorta, qué se
 * vuelve traslúcido.
 *
 * @param {{
 *   raiz: any, escena: any, porNivel: Map<number, any>,
 *   planos: any[], huella: {ancho: number, fondo: number},
 *   modo: string, soloNivel: number|null
 * }} v
 */
export function aplicarModoDeVista(v) {
  //  1. EN RAYOS X LA CUBIERTA SE APAGA, no se vuelve traslúcida.
  //
  //     Volverla traslúcida sobre tres losas también traslúcidas apila cuatro
  //     capas de transparencia y el resultado es una niebla lechosa donde no
  //     se distingue ningún piso. Y antes de este arreglo la cubierta quedaba
  //     OPACA: el botón respondía, el modo cambiaba, y en pantalla no pasaba
  //     nada — la peor forma de fallar, porque parece que la función no existe.
  for (const hijo of v.raiz.children) {
    if (hijo.userData?.esCubierta) hijo.visible = v.modo !== 'rayosX';
  }

  //  2. El corte se lleva algo más de un tercio del frente: lo suficiente para
  //     ver dentro de los tres pisos, y poco como para que el edificio siga
  //     leyéndose como un volumen y no como media maqueta.
  v.planos[0].constant = v.huella.ancho * 0.62;
  v.planos[1].constant = v.huella.fondo * 0.62;

  //  3. El recorte se aplica a TODOS los materiales: un muro recortado junto a
  //     un escritorio entero deja un escritorio flotando en el aire.
  const recorta = v.modo === 'corte' && v.soloNivel === null;
  v.escena.traverse((o) => {
    if (!o.isMesh) return;
    const materiales = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of materiales) {
      if (!m) continue;
      m.clippingPlanes = recorta ? v.planos : null;
      m.clipIntersection = true;
      m.needsUpdate = true;
    }
  });

  //  4. Las losas de los pisos de arriba, traslúcidas en rayos X. La de abajo
  //     nunca: no tiene nada debajo que mostrar y volverla traslúcida deja ver
  //     la explanada a través del edificio.
  if (v.porNivel.size === 0) return;
  const elDeAbajo = Math.min(...v.porNivel.keys());
  for (const [nivel, g] of v.porNivel) {
    const losa = g.userData?.losa;
    if (!losa) continue;
    const atenuada = v.modo === 'rayosX' && nivel !== elDeAbajo;
    losa.material.transparent = atenuada;
    losa.material.opacity = atenuada ? 0.18 : 1;
    losa.material.depthWrite = !atenuada;
    losa.castShadow = !atenuada;
    losa.material.needsUpdate = true;
  }
}
