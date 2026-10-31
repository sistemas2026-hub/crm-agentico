/**
 * EL EDIFICIO: CÓMO SE APILAN LOS NIVELES DE UNA EMPRESA.
 *
 * Hasta acá la empresa entera era una REJILLA PLANA: once salas una al lado de
 * la otra sobre un mismo suelo. Se veían todas y no se parecía a una empresa —
 * eran oficinas flotando. Los pisos ya eran un dato de la configuración y la
 * pantalla no los usaba para nada más que agrupar un selector.
 *
 * Esto los usa. Cada nivel es una **bandeja**: una losa con su franja de
 * circulación al fondo, sus salas al frente y un núcleo vertical en un extremo.
 * Las bandejas se apilan restando altura, que es lo que la isometría hace con
 * `gz`.
 *
 * POR QUÉ LAS SALAS VAN AL FRENTE Y LA CIRCULACIÓN AL FONDO
 * ---------------------------------------------------------
 * No es estética: es la única disposición en la que un edificio de verdad deja
 * ver sus pisos. En esta proyección la pantalla pone `y = 16·(gx+gy) − 26·gz`,
 * así que un nivel más alto se dibuja MÁS ARRIBA y tapa del nivel de abajo
 * justamente la zona de `gx+gy` pequeño — el FONDO.
 *
 * Si las salas estuvieran al fondo, el piso de arriba les taparía los
 * escritorios. Con la circulación al fondo, lo que se tapa es el pasillo, que
 * es lo que menos información lleva. Es la misma aritmética que hizo que el
 * hueco entre salas vecinas tenga que medirse contra la ALTURA del muro y no
 * contra el suelo.
 *
 * Y es la razón por la que esto no se resolvió «separando más los pisos». Para
 * que dos bandejas no se solapen nada, la separación tendría que ser mayor que
 * la diagonal proyectada de una bandeja entera —más de treinta unidades de
 * altura, contra las cuatro que mide un muro—. Un edificio así son tres
 * rebanadas lejanísimas unidas por un hilo: otra vez oficinas flotando, con
 * más pasos intermedios.
 *
 * LO QUE ESTE ARCHIVO NO DECIDE
 * Cuántos pisos hay, cuáles son y qué va en cada uno: eso es la organización de
 * la empresa y llega del motor. Acá sólo se calcula DÓNDE cae cada cosa, y se
 * calcula — no hay un mapa de coordenadas escrito a mano, porque las salas no
 * miden lo mismo y una empresa puede declarar cuatro o quince.
 */

import { plantaDe } from './departamentos.js';

/**
 * Cuánta altura hay entre la losa de un nivel y la del siguiente.
 *
 * QUINCE, Y SALE DE UNA MEDICIÓN, NO DE UN GUSTO.
 * ------------------------------------------------
 * Se empezó con seis —un muro mide cuatro, más el canto y algo de aire— y la
 * prueba de `edificio.test.js` lo tiró: **los escritorios de los pisos 1 y 2
 * quedaban detrás de la losa del piso de arriba**. No daba error, no daba
 * aviso, y la escena los seguía animando: un agente trabajando donde nadie lo
 * ve.
 *
 * Invirtiendo la proyección sale la condición exacta. Un punto a altura `z` del
 * nivel de abajo cae, sobre el plano del nivel de arriba, en la celda
 * `GY + (H − z)·0,8125`; para que no lo tape tiene que caer PASADO el frente de
 * las salas de arriba. Los dos desplazamientos del nivel se cancelan y queda:
 *
 *     (H − z) · 0,8125  >  fondo de la sala − gy del puesto
 *
 * O sea que **lo que fija la separación no es la altura del muro ni la
 * profundidad del pasillo: es cuánta sala queda DETRÁS del escritorio.** Con
 * salas de diez celdas y puestos a 2,4, el mínimo es 13 para la placa de un
 * puesto —que va más alta que la silla y por eso es el caso que manda—. Quince
 * deja 1,6 celdas de margen.
 *
 * Y es la razón por la que el hueco NO se cierra bajando este número: bajarlo
 * tapa puestos. Lo que se hace con el aire que queda es LLENARLO DE ESTRUCTURA
 * —el núcleo, las columnas que suben hasta la losa de arriba—, que es lo que
 * distingue un edificio en sección de tres bandejas flotando.
 */
export const ALTURA_DE_PISO = 15;

/**
 * El hueco entre dos salas vecinas del mismo nivel.
 *
 * Cinco celdas, medido: con tres, los muros de una sala se metían dentro de la
 * vecina. En isometría un muro de cuatro unidades se proyecta más de cien
 * píxeles hacia arriba e invade la sala de atrás aunque en planta no se toquen.
 */
export const SEPARACION_SALAS = 5;

/** Cuántas celdas de circulación lleva cada nivel, al fondo de sus salas. */
export const FONDO_DE_CIRCULACION = 5;

/** La huella del núcleo vertical: escaleras y ascensor. */
export const NUCLEO = { ancho: 6, fondo: 4 };

/**
 * La franja de circulación de un nivel: una losa sin muros.
 *
 * NO es una sala y por eso no tiene puestos ni cartel: es el suelo por el que
 * se pasa. Sin muros a propósito — una fachada que tape las oficinas es
 * exactamente lo que un edificio isométrico no puede tener.
 *
 * @param {number} ancho celdas de ancho, el frente completo del nivel
 */
function circulacion(ancho, acento, hastaDondeSostiene, alturaColumna) {
  const w = Math.max(4, Math.round(ancho));
  //  LAS COLUMNAS SON LO QUE CIERRA EL EDIFICIO.
  //
  //  Suben desde esta losa hasta la de arriba, cada seis celdas. Sin ellas los
  //  quince de separación son aire y los niveles se leen como bandejas
  //  flotando —la crítica exacta que trajo esta etapa—. Con ellas, ese aire es
  //  la altura libre de una planta y lo que se ve entre dos losas es la
  //  estructura que las sostiene.
  //
  //  Y SOLO HASTA DONDE HAY ALGO QUE SOSTENER. El último nivel no lleva
  //  ninguna —la cubierta no tiene otra losa encima— y los demás las llevan
  //  únicamente bajo la huella del nivel de arriba.
  //
  //  Se vio en el navegador: el piso 1 tiene cinco salas y el 2 tiene tres, así
  //  que las columnas del tramo largo del 1 subían quince unidades hasta el
  //  aire. Colgaban a la derecha del edificio y se leían exactamente como lo
  //  que eran, postes.
  const alcance = Math.max(0, Math.min(w, hastaDondeSostiene ?? 0));
  const columnas = Array.from(
    { length: Math.max(0, Math.floor((alcance - 1.2) / 6) + 1) },
    (_, i) => ({ tipo: 'columna', gx: 1.2 + i * 6, gy: 1.1,
                 alto: alturaColumna ?? ALTURA_DE_PISO })
  );
  return {
    mundo: { ancho: w, fondo: FONDO_DE_CIRCULACION, alto: 0 },
    acento,
    //  Todo el suelo es paso: es lo que lo distingue de una sala de un vistazo.
    pasillo: { desde: 0, hasta: w },
    cartel: null,
    mural: null,
    muros: false,
    losa: true,
    //  Baranda en el borde abierto: es lo que convierte un suelo que termina en
    //  el aire en una planta de un edificio. Sin ella el nivel parece cortado.
    baranda: true,
    mobiliario: columnas,
    puestos: []
  };
}

/**
 * El núcleo vertical de un nivel: escaleras, ascensor y su rellano.
 *
 * Uno por nivel, todos en la misma huella, así que al apilarlos la caja queda
 * alineada y se lee como un núcleo continuo. Es lo que une los pisos: sin él,
 * tres bandejas apiladas son tres bandejas apiladas.
 */
function nucleo(acento, altura) {
  return {
    //  El muro del núcleo sube la ALTURA DE PISO entera, no cuatro unidades:
    //  así el remate de un nivel llega justo a la losa del siguiente y los
    //  núcleos apilados se leen como una caja continua. Con cuatro, cada
    //  núcleo era una cabina suelta en el aire.
    mundo: { ancho: NUCLEO.ancho, fondo: NUCLEO.fondo, alto: altura },
    acento,
    pasillo: { desde: 0, hasta: NUCLEO.ancho },
    cartel: null,
    mural: null,
    //  CON muros: el núcleo es lo único cerrado del edificio, y esos dos
    //  paneles son los que le dan volumen a la caja vertical.
    muros: true,
    losa: true,
    baranda: false,
    mobiliario: [
      //  Dos tramos de escalera con su descanso: una planta de quince
      //  unidades no se sube en un tramo, y un tramo único de quince queda con
      //  una pendiente que no es de una escalera.
      { tipo: 'escalera', gx: 0.5, gy: 0.4, alto: altura / 2, peldanos: 8 },
      { tipo: 'escalera', gx: 2.6, gy: 0.4, alto: altura / 2, peldanos: 8,
        desde: altura / 2 },
      { tipo: 'ascensor', gx: 4.1, gy: 0.5, alto: altura - 1 },
      { tipo: 'columna', gx: 5.1, gy: 3.0, alto: altura }
    ],
    puestos: []
  };
}

/**
 * El edificio de una empresa: sus niveles apilados, listos para montar.
 *
 * Devuelve las plantas Y los niveles. Las dos cosas, porque quien dibuja
 * necesita plantas y quien navega necesita saber qué planta pertenece a qué
 * nivel — y deducirlo después, comparando coordenadas, sería reconstruir a mano
 * algo que acá se sabe con certeza.
 *
 * @param {any[]} salas las salas de la empresa, ya compuestas
 * @param {any[]} agentes el inventario del motor
 * @param {any[]} pisos los niveles declarados, de arriba hacia abajo
 * @param {{ soloNivel?: number|null }} [opciones] para aislar un nivel
 */
export function edificioDe(salas, agentes, pisos, opciones = {}) {
  const lista = Array.isArray(salas) ? salas : [];
  const niveles = Array.isArray(pisos) ? pisos : [];
  const soloNivel = opciones.soloNivel ?? null;

  if (lista.length === 0 || niveles.length === 0) {
    return { plantas: [], niveles: [], mundo: { ancho: 0, fondo: 0, alto: 0 } };
  }

  //  El nivel más bajo es la referencia de altura. Se calcula del dato y no se
  //  asume que el más bajo sea 1: una empresa puede declarar un sótano.
  const nivelMinimo = Math.min(...niveles.map((p) => p.nivel));

  //  El ancho del edificio es el del nivel más largo. Todos los niveles
  //  comparten frente para que la fachada no sea una escalera: un nivel corto
  //  deja su losa más corta y se ve, que es honesto, pero la circulación
  //  llega hasta el frente común.
  const anchoDeNivel = new Map();
  for (const piso of niveles) {
    const suyas = piso.salas ?? lista.filter((s) => s.piso === piso.nivel);
    const ancho = suyas.reduce(
      (acc, s, i) => acc + s.planta.mundo.ancho + (i > 0 ? SEPARACION_SALAS : 0), 0);
    anchoDeNivel.set(piso.nivel, ancho);
  }
  //  CADA NIVEL MIDE LO SUYO, no lo del más largo.
  //
  //  Se probó al revés —todos los niveles con el frente común, para que la
  //  fachada no fuera una escalera— y en el navegador se vio por qué está mal:
  //  los pisos con tres salas arrastraban una cubierta vacía tan larga como el
  //  piso de cinco, y el edificio se leía como tres andenes desiertos con unas
  //  salas apretadas en una punta.
  //
  //  Un nivel con menos salas es MÁS CORTO, y eso es información verdadera
  //  sobre la empresa. El escalonado que produce es el de un edificio
  //  escalonado, no un defecto.

  const plantas = [];
  const detalle = [];

  for (const piso of niveles) {
    if (soloNivel !== null && piso.nivel !== soloNivel) continue;

    //  La altura del nivel. Aislado, el nivel baja al suelo: mirar un piso
    //  solo flotando a dos pisos de altura no dice nada, y encuadrar sobre el
    //  vacío deja la sala en una esquina.
    const gz = soloNivel !== null ? 0 : (piso.nivel - nivelMinimo) * ALTURA_DE_PISO;
    const suyas = piso.salas ?? lista.filter((s) => s.piso === piso.nivel);
    const acento = suyas[0]?.planta?.acento;
    const ids = [];

    //  1. El núcleo, pegado al borde izquierdo y al fondo.
    //
    //     Ahí y no en medio de la circulación por la misma aritmética de
    //     siempre: en esa columna de pantalla el nivel de arriba sólo tiene su
    //     PROPIO núcleo, así que la caja vertical no se tapa a sí misma — se
    //     continúa. Puesto entre las salas, el piso de arriba se lo comería.
    //  El nivel que esta planta sostiene, si hay alguno. Es el inmediatamente
    //  superior de los DECLARADOS, no `nivel + 1`: una empresa puede declarar
    //  el 1 y el 3 sin el 2.
    const encima = niveles
      .map((p) => p.nivel)
      .filter((n) => n > piso.nivel)
      .sort((a, b) => a - b)[0];
    const sostiene = encima === undefined
      ? 0
      : (anchoDeNivel.get(encima) || 0) + SEPARACION_SALAS;
    plantas.push({
      ...nucleo(acento, soloNivel !== null ? 5 : ALTURA_DE_PISO),
      origen: { gx: 0, gy: 0, gz },
      nivel: piso.nivel,
      papel: 'nucleo'
    });

    //  2. La franja de circulación, al fondo y arrancando donde termina el
    //     núcleo: así el rellano y el pasillo se tocan y se lee que se pasa de
    //     uno al otro.
    plantas.push({
      //  AISLADO, LA COLUMNA ES UN MUÑÓN. Con el nivel de arriba fuera de la
      //  escena, una columna de quince unidades sube hasta el vacío: en el
      //  navegador se veían como mástiles y se comían la sala. Cortada a dos y
      //  media sigue diciendo que el edificio continúa, que es lo único que
      //  tiene que decir cuando lo de arriba no se está mirando.
      ...circulacion((anchoDeNivel.get(piso.nivel) || NUCLEO.ancho) + SEPARACION_SALAS,
                     acento, sostiene, soloNivel !== null ? 2.5 : undefined),
      origen: { gx: NUCLEO.ancho, gy: 0, gz },
      nivel: piso.nivel,
      papel: 'circulacion'
    });

    //  3. Las salas, al frente, una al lado de la otra.
    let gx = NUCLEO.ancho + SEPARACION_SALAS;
    for (const sala of suyas) {
      plantas.push({
        ...plantaDe(sala, agentes),
        origen: { gx, gy: FONDO_DE_CIRCULACION, gz },
        //  LOSA Y BARANDA SOLO EN EL EDIFICIO. Una sala mirada sola se sigue
        //  viendo exactamente como se veía: su suelo llega hasta el borde del
        //  encuadre y no termina en el aire, así que un canto de forjado ahí
        //  sería un reborde sin motivo. Son dos campos de la planta y no una
        //  decisión de la sala, justamente para que esto se pueda elegir acá.
        losa: true,
        baranda: true,
        //  EL NOMBRE VA EN EL CANTO DE LA LOSA, al frente.
        //
        //  El cartel del muro de fondo sigue ahí y se lee al mirar la sala
        //  sola, pero en el edificio queda detrás de la losa de arriba: con la
        //  separación medida, el muro de fondo sólo se ve hasta 2,7 de sus 4
        //  unidades. Un nombre que a veces se ve no es un nombre.
        //
        //  Y en el canto se lee mejor de lejos, que es como se mira un
        //  edificio entero: es el directorio de la planta, no un rótulo de
        //  pared.
        rotuloFrontal: sala.rotulo,
        nivel: piso.nivel,
        papel: 'sala',
        sala: sala.id
      });
      ids.push(sala.id);
      gx += sala.planta.mundo.ancho + SEPARACION_SALAS;
    }

    detalle.push({
      nivel: piso.nivel,
      rotulo: piso.rotulo ?? '',
      declarado: piso.declarado !== false,
      gz,
      salas: ids
    });
  }

  //  El recinto que la cámara tiene que encuadrar. Se calcula de lo que hay y
  //  no del frente declarado: con un nivel aislado el edificio es otro.
  const mundo = plantas.reduce((acc, p) => ({
    ancho: Math.max(acc.ancho, p.origen.gx + p.mundo.ancho),
    fondo: Math.max(acc.fondo, p.origen.gy + p.mundo.fondo),
    alto: Math.max(acc.alto, p.origen.gz + p.mundo.alto)
  }), { ancho: 0, fondo: 0, alto: 0 });

  return { plantas, niveles: detalle, mundo };
}
