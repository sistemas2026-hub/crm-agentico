/**
 * LAS FIGURAS DE AMBIENTE: gente que camina por la sede y no trabaja ahí.
 *
 * QUÉ SON Y QUÉ NO SON
 * --------------------
 * El 01/11/2026 se decidió que los personajes pueden caminar, sentarse y
 * moverse sin que haya un hecho laboral detrás, con una condición escrita con
 * esas palabras: *«estos movimientos deben tener procedencia `ambiente` y
 * nunca registrarse como actividad operativa real»*. Esto es ese permiso,
 * acotado a lo mínimo que lo hace seguro.
 *
 * Una figura de ambiente **no es un agente**. No ocupa un puesto declarado, no
 * lleva placa de nombre, no se puede seleccionar, no abre ficha, no aparece en
 * ningún contador y no produce un solo acontecimiento. Es mobiliario que se
 * mueve, y se dibuja por el mismo motivo que una planta en una maceta: una
 * oficina sin nadie cruzándola se lee como una maqueta.
 *
 * LA LÍNEA QUE NO SE CRUZA
 * ------------------------
 * La regla del proyecto es no inventar empleados. Una figura que caminara con
 * un nombre encima, o que se sentara en un escritorio declarado, estaría
 * afirmando que alguien trabaja ahí — y eso es exactamente lo prohibido. Por
 * eso estas figuras **sólo recorren la circulación**: el patio, la entrada y
 * los pasillos entre manzanas. Donde hay escritorios, no entran.
 *
 * Y hay una segunda razón, de dibujo: el mundo ordena sus hijos por `zIndex`,
 * así que una figura a nivel de mundo se pinta entera delante o detrás de una
 * sala, nunca entremezclada con sus muebles. Caminando por la circulación eso
 * es correcto; dentro de una sala se vería atravesando una pared.
 *
 * CUÁNTAS, Y DE DÓNDE SALE ESE NÚMERO
 * -----------------------------------
 * Del TAMAÑO de la sede y nunca de sus datos. Si el número saliera de cuántos
 * agentes hay, o de cuántos están ejecutando, la escena estaría diciendo algo
 * sobre la empresa con figuras que no representan a nadie — y quien la mire
 * leería una señal donde no la hay.
 */

/** Cuánto avanza una figura por segundo, en celdas. */
export const PASO = 1.6;

/** Lo que se queda quieta al llegar a un destino, en segundos. */
export const PAUSA = { minima: 1.5, maxima: 4.5 };

/** Una figura cada tantas unidades cuadradas de circulación. */
export const DENSIDAD = 320;

/** Nunca menos de una ni más de estas, por muy grande que sea la sede. */
export const CUANTAS = { minimo: 1, maximo: 6 };

/**
 * Los oficios que se ven cruzando una sede, y que no son de nadie en concreto.
 *
 * Son etiquetas de DIBUJO —de qué color va la figura y qué lleva— y no roles
 * de la empresa: ninguno existe en la configuración, ninguno se puede
 * seleccionar y ninguno aparece en un contador. Si mañana una empresa declara
 * un departamento de aseo, sus personas saldrán de sus puestos declarados como
 * cualquier otra, no de acá.
 */
export const OFICIOS = ['aseo', 'bodega', 'visita'];

/**
 * Cuántas figuras le corresponden a una superficie de circulación.
 *
 * @param {number} area en unidades cuadradas
 */
export function cuantasFiguras(area) {
  const n = Math.round((Number.isFinite(area) ? Math.max(0, area) : 0) / DENSIDAD);
  return Math.min(CUANTAS.maximo, Math.max(CUANTAS.minimo, n));
}

/**
 * Un número pseudoaleatorio estable a partir de una semilla entera.
 *
 * Estable y no `Math.random()`: la sede tiene que verse igual en dos cargas
 * seguidas. Con azar de verdad, dos capturas del mismo estado saldrían
 * distintas y no habría forma de comparar una contra otra —que es como se
 * verifica todo lo demás en este repositorio—.
 *
 * @param {number} semilla
 */
export function azar(semilla) {
  const x = Math.sin(semilla * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Las figuras iniciales para una sede.
 *
 * @param {{x: number, y: number, ancho: number, fondo: number}[]} zonas
 *        los rectángulos de circulación por los que se puede caminar
 */
export function poblar(zonas) {
  const sitios = (Array.isArray(zonas) ? zonas : []).filter(
    (z) => z && z.ancho > 2 && z.fondo > 2);
  if (sitios.length === 0) return [];

  const area = sitios.reduce((t, z) => t + z.ancho * z.fondo, 0);
  const cuantas = cuantasFiguras(area);

  return Array.from({ length: cuantas }, (_, i) => {
    const zona = sitios[i % sitios.length];
    const desde = puntoEn(zona, i * 7 + 1);
    return {
      id: `ambiente-${i}`,
      oficio: OFICIOS[i % OFICIOS.length],
      //  Arranca donde va a estar, no en una esquina: un grupo de figuras
      //  saliendo todas del mismo punto al cargar se lee como un error.
      x: desde.x,
      y: desde.y,
      destino: puntoEn(sitios[(i + 1) % sitios.length], i * 13 + 5),
      //  Escalonadas: si todas arrancan a la vez caminan en bloque, como un
      //  desfile, y eso no se parece a una oficina.
      espera: azar(i * 31 + 3) * PAUSA.maxima,
      semilla: i * 101 + 7
    };
  });
}

/**
 * Un punto dentro de una zona, con margen para no pegarse a los bordes.
 *
 * @param {{x: number, y: number, ancho: number, fondo: number}} zona
 * @param {number} semilla
 */
export function puntoEn(zona, semilla) {
  const margen = 1.2;
  const ancho = Math.max(0, zona.ancho - margen * 2);
  const fondo = Math.max(0, zona.fondo - margen * 2);
  return {
    x: zona.x + margen + azar(semilla) * ancho,
    y: zona.y + margen + azar(semilla + 0.5) * fondo
  };
}

/**
 * Avanza una figura `dt` segundos.
 *
 * Devuelve una figura NUEVA y no muta la que recibe: la escena guarda la
 * anterior para interpolar, y mutarla dejaría a la figura comparándose consigo
 * misma y quieta.
 *
 * @param {any} figura
 * @param {number} dt segundos
 * @param {{x: number, y: number, ancho: number, fondo: number}[]} zonas
 */
export function avanzar(figura, dt, zonas) {
  const paso = Math.max(0, Number.isFinite(dt) ? dt : 0);
  if (figura.espera > 0) {
    return { ...figura, espera: figura.espera - paso, andando: false };
  }

  const dx = figura.destino.x - figura.x;
  const dy = figura.destino.y - figura.y;
  const falta = Math.hypot(dx, dy);

  if (falta < 0.25) {
    //  Llegó: se queda un rato y elige otro sitio. La pausa es lo que
    //  distingue a alguien que trabaja de alguien que patrulla en círculos.
    const sitios = (Array.isArray(zonas) ? zonas : []).filter((z) => z && z.ancho > 2);
    const siguiente = sitios.length
      ? puntoEn(sitios[Math.floor(azar(figura.semilla) * sitios.length)], figura.semilla + 1)
      : figura.destino;
    return {
      ...figura,
      x: figura.destino.x,
      y: figura.destino.y,
      destino: siguiente,
      espera: PAUSA.minima + azar(figura.semilla + 2) * (PAUSA.maxima - PAUSA.minima),
      semilla: figura.semilla + 17,
      andando: false
    };
  }

  const avance = Math.min(falta, PASO * paso);
  return {
    ...figura,
    x: figura.x + (dx / falta) * avance,
    y: figura.y + (dy / falta) * avance,
    andando: true
  };
}
