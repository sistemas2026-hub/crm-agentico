/**
 * EL PASEO DE UN PERSONAJE: levantarse, caminar y volver a sentarse.
 *
 * QUÉ ES, Y SOBRE TODO QUÉ NO ES
 * ------------------------------
 * Esto es **locomoción ambiental**. Un personaje se levanta porque pasó un
 * rato, camina un tramo del pasillo y vuelve a su silla. No pasó nada: ningún
 * hecho de trabajo hay detrás. El paseo lleva `procedencia: 'ambiente'` y no
 * produce un solo acontecimiento.
 *
 * Esa línea es la misma que ya separaba a las figuras del patio de quien
 * trabaja, y acá importa más porque ahora **sí** se mueve alguien que ocupa un
 * puesto declarado. Si un paseo se registrara como actividad, la pantalla
 * estaría afirmando que esa persona hizo algo —y quien la mire no tendría
 * forma de distinguirlo de un trabajo de verdad—.
 *
 * Lo que este archivo NO sabe: de quién es el puesto, de qué área es, con qué
 * trabaja, si está ejecutando algo. Recibe un identificador de puesto y una
 * ruta de celdas, y devuelve dónde está el cuerpo en cada instante. Lo vigila
 * `navegacion.test.js`, que prohíbe el vocabulario del negocio en este archivo
 * —comentarios incluidos— para que el mismo código sirva el día que caminen
 * visitantes o personal humano.
 *
 * NO TODOS A LA VEZ, Y NO SIEMPRE
 * -------------------------------
 * Entre paseo y paseo pasa entre `ESPERA.minima` y `ESPERA.maxima` segundos, y
 * cada personaje arranca con una espera distinta sacada de su semilla. Si
 * todos se levantaran juntos, la oficina se leería como una coreografía — y
 * una oficina donde todos hacen lo mismo al mismo tiempo no se parece a una
 * oficina.
 *
 * NADA SE TELETRANSPORTA
 * ----------------------
 * La posición se interpola entre dos celdas consecutivas de la ruta. Un salto
 * de una celda a otra a 0,5 de distancia se ve como un parpadeo, y a esta
 * escala se nota.
 */

/** Los estados del ciclo, en el orden en que se recorren. */
export const ESTADOS = ['sentado', 'levantandose', 'yendo', 'volviendo', 'sentandose'];

/** Lo que avanza el cuerpo por segundo, en unidades del plano. */
export const VELOCIDAD = 1.5;

/** Lo que tarda en ponerse de pie, y lo mismo en sentarse. */
export const TRANSICION = 0.7;

/**
 * Lo que pasa entre un paseo y el siguiente, en segundos.
 *
 * LARGO, Y MÁS DE LO QUE PARECÍA NECESARIO. La primera versión esperaba entre
 * 20 y 90 segundos, que suena de sobra para un paseo de dieciséis. Medido en
 * el navegador sobre tres minutos: **había alguien fuera de su silla el 68%
 * del tiempo**, en cuatro paseos.
 *
 * La cuenta explica por qué, y no es el largo del paseo: con ocho puestos
 * ocupados y una espera media de 55 segundos, cada persona quiere levantarse
 * una vez cada 72, así que el turno —uno a la vez— se satura. Acortar la ruta
 * no cambia eso; lo que lo cambia es cuántas ganas hay de salir.
 *
 * Con 60 a 180 el ciclo de cada uno pasa a unos 137 segundos: **su escritorio
 * está vacío uno de cada ocho minutos**, que es lo que se parece a una
 * oficina. Que el pasillo tenga casi siempre a alguien no es un problema — es
 * justamente lo que hace que el edificio no parezca una maqueta.
 */
export const ESPERA = { minima: 60, maxima: 180 };

/** Azar estable: la escena tiene que verse igual en dos cargas seguidas. */
export function azar(semilla) {
  const x = Math.sin(semilla * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Un paseo recién creado, sentado y esperando.
 *
 * @param {string} puesto el identificador del puesto. Es lo ÚNICO que se sabe
 *   de quién pasea: ni su nombre, ni a qué se dedica, ni de qué área es.
 * @param {number} semilla
 */
export function crearPaseo(puesto, semilla) {
  return {
    puesto,
    //  LA PROCEDENCIA VIAJA CON EL DATO y no en un comentario: quien reciba
    //  esto tiene que poder decir que es ambiente sin preguntarle a nadie.
    procedencia: 'ambiente',
    estado: 'sentado',
    //  Escalonados: cada uno espera lo suyo desde el primer segundo.
    espera: ESPERA.minima + azar(semilla) * (ESPERA.maxima - ESPERA.minima),
    semilla,
    ruta: null,
    tramo: 0,
    avance: 0,
    fase: 0,
    //  Dónde está el cuerpo. Mientras está sentado es `null`: lo dibuja su
    //  silla, y una posición inventada para alguien que no se movió sería un
    //  dato que no significa nada.
    donde: null
  };
}

/** ¿Está este paseo fuera de su silla? */
export function enPie(paseo) {
  return paseo.estado === 'yendo' || paseo.estado === 'volviendo'
    || paseo.estado === 'levantandose' || paseo.estado === 'sentandose';
}

/**
 * Cuánto hay que mezclar al caminante con el personaje sentado, de 0 a 1.
 *
 * Es lo que evita el salto: el cuerpo sentado se desvanece mientras el que
 * camina aparece, en el mismo sitio y en el mismo medio segundo.
 */
export function mezcla(paseo) {
  if (paseo.estado === 'levantandose') return Math.min(1, paseo.fase / TRANSICION);
  if (paseo.estado === 'sentandose') return Math.max(0, 1 - paseo.fase / TRANSICION);
  return enPie(paseo) ? 1 : 0;
}

/** El largo de una ruta, en unidades del plano. */
function largoDe(ruta, celda) {
  let total = 0;
  for (let i = 1; i < ruta.length; i++) {
    total += Math.hypot(ruta[i].cx - ruta[i - 1].cx, ruta[i].cy - ruta[i - 1].cy) * celda;
  }
  return total;
}

/**
 * Dónde está el cuerpo sobre una ruta, a `avance` unidades del principio.
 *
 * @returns {{gx: number, gy: number, tramo: number} | null}
 */
export function puntoEnRuta(ruta, avance, celda) {
  if (!Array.isArray(ruta) || ruta.length === 0) return null;
  if (ruta.length === 1) {
    return { gx: (ruta[0].cx + 0.5) * celda, gy: (ruta[0].cy + 0.5) * celda, tramo: 0 };
  }
  let resto = Math.max(0, avance);
  for (let i = 1; i < ruta.length; i++) {
    const a = ruta[i - 1];
    const b = ruta[i];
    const d = Math.hypot(b.cx - a.cx, b.cy - a.cy) * celda;
    if (resto <= d || i === ruta.length - 1) {
      const k = d === 0 ? 1 : Math.min(1, resto / d);
      return {
        gx: (a.cx + (b.cx - a.cx) * k + 0.5) * celda,
        gy: (a.cy + (b.cy - a.cy) * k + 0.5) * celda,
        tramo: i - 1
      };
    }
    resto -= d;
  }
  const u = ruta[ruta.length - 1];
  return { gx: (u.cx + 0.5) * celda, gy: (u.cy + 0.5) * celda, tramo: ruta.length - 2 };
}

/**
 * Avanza un paseo `dt` segundos.
 *
 * Devuelve un paseo NUEVO y no muta el que recibe, igual que `ambiente.js`: la
 * escena guarda el anterior para interpolar.
 *
 * @param {any} paseo
 * @param {number} dt segundos
 * @param {{celda: number, planear: () => {ida: any[], vuelta: any[]} | null}} mundo
 *   `planear` se llama cuando el personaje decide levantarse, y devuelve las
 *   dos rutas o `null` si no hay. Es una función y no un dato para que este
 *   archivo no tenga que importar la rejilla ni saber de A*.
 */
export function avanzar(paseo, dt, mundo) {
  const paso = Math.max(0, Number.isFinite(dt) ? dt : 0);
  const celda = mundo?.celda ?? 0.5;

  if (paseo.estado === 'sentado') {
    const espera = paseo.espera - paso;
    if (espera > 0) return { ...paseo, espera, donde: null };
    const rutas = mundo?.planear?.() ?? null;
    //  SIN RUTA NO SE LEVANTA. Si el plano cambió y ya no hay camino, el
    //  personaje se queda donde está y lo vuelve a intentar más tarde. Lo que
    //  no hace nunca es salir igual: eso es lo que termina con alguien
    //  cruzando una pared.
    if (!rutas || !rutas.ida || rutas.ida.length < 2) {
      return { ...paseo, espera: ESPERA.minima, donde: null };
    }
    return {
      ...paseo,
      estado: 'levantandose',
      fase: 0,
      ruta: rutas.ida,
      rutaVuelta: rutas.vuelta ?? [...rutas.ida].reverse(),
      tramo: 0,
      avance: 0,
      donde: puntoEnRuta(rutas.ida, 0, celda)
    };
  }

  if (paseo.estado === 'levantandose' || paseo.estado === 'sentandose') {
    const fase = paseo.fase + paso;
    if (fase < TRANSICION) return { ...paseo, fase };
    if (paseo.estado === 'levantandose') {
      return { ...paseo, estado: 'yendo', fase: 0, avance: 0 };
    }
    //  Terminó de sentarse: a esperar otra vez, con una espera nueva.
    return {
      ...paseo,
      estado: 'sentado',
      fase: 0,
      ruta: null,
      rutaVuelta: null,
      avance: 0,
      donde: null,
      semilla: paseo.semilla + 31,
      espera: ESPERA.minima + azar(paseo.semilla + 31) * (ESPERA.maxima - ESPERA.minima)
    };
  }

  //  Caminando, de ida o de vuelta.
  const ruta = paseo.estado === 'yendo' ? paseo.ruta : paseo.rutaVuelta;
  if (!Array.isArray(ruta) || ruta.length < 2) {
    //  La ruta dejó de valer mientras caminaba. Se sienta donde pueda en vez
    //  de seguir avanzando sobre un camino que ya no existe.
    return { ...paseo, estado: 'sentandose', fase: 0 };
  }
  const largo = largoDe(ruta, celda);
  const avance = paseo.avance + VELOCIDAD * paso;
  if (avance >= largo) {
    if (paseo.estado === 'yendo') {
      return {
        ...paseo,
        estado: 'volviendo',
        avance: 0,
        donde: puntoEnRuta(paseo.rutaVuelta, 0, celda)
      };
    }
    return { ...paseo, estado: 'sentandose', fase: 0, avance: largo };
  }
  const donde = puntoEnRuta(ruta, avance, celda);
  return { ...paseo, avance, donde, tramo: donde?.tramo ?? 0 };
}

/**
 * A quién le toca pasear, de entre los puestos ocupados.
 *
 * COMO MUCHO UNO A LA VEZ, y es deliberado. La primera etapa pide «un solo
 * personaje» y el motivo sobrevive a la primera etapa: con cinco caminando, lo
 * que se ve es tráfico, y el ojo deja de seguir a ninguno. Cuando se suba este
 * número habrá que mirarlo en el navegador, no deducirlo.
 */
export const PASEANDO_A_LA_VEZ = 1;

/** ¿Puede este paseo arrancar, dado lo que ya hay en marcha? */
export function puedeArrancar(paseos) {
  return paseos.filter((p) => enPie(p)).length < PASEANDO_A_LA_VEZ;
}
