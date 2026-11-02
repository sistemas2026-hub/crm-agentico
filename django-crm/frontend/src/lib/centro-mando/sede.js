/**
 * LA SEDE: todos los departamentos en una planta, lista para dibujar.
 *
 * Es la composición que se decidió el 01/11/2026 mirando la referencia: una
 * planta abierta con plaza al frente, los departamentos alrededor, y la
 * navegación por traslado —uno se acerca al departamento— en vez de por
 * cambio de piso.
 *
 * QUÉ SE GANA, Y NO ES SOLO ESTÉTICO
 * ----------------------------------
 * Sin pisos apilados **no hay nada encima de nada**, y con eso desaparece toda
 * la aritmética que costó la semana: la desigualdad de oclusión de
 * `edificio.js`, la altura de piso mínima, la cubierta que escondía nueve
 * puestos, los 38 de separación que habrían hecho una torre de 114. Ninguna de
 * esas cosas es un problema resuelto acá: es un problema que deja de existir.
 *
 * El precio es que se pierde la jerarquía de los pisos —P1 Administración, P2
 * Operación, P3 Tecnología—. Sigue en el dato: cada sala conserva su `piso`, y
 * el día que haga falta se puede leer como zona dentro del mismo plano sin
 * tocar la geometría.
 *
 * Devuelve el MISMO contrato que `edificioDe`: `plantas`, `niveles` y `mundo`.
 * La escena no tiene por qué saber qué composición está dibujando, y mientras
 * no lo sepa se puede comparar una contra otra con los mismos personajes, la
 * misma ficha y las mismas pruebas.
 */

import { plantaDe } from './departamentos.js';
import { ENTRADA, PASILLO, repartirAnillo } from './anillo.js';
import { mobiliarioDeEntrada, mobiliarioDePatio } from './patio.js';

/** Lo que sube un muro de sala. */
export const ALTURA_DE_MURO = 4;

/**
 * La sede de una empresa en una sola planta.
 *
 * @param {any[]} salas las salas de la empresa, ya compuestas
 * @param {any[]} agentes el inventario del motor
 * @param {{ soloSala?: string|null }} [opciones]
 */
export function sedeDe(salas, agentes, opciones = {}) {
  const lista = Array.isArray(salas) ? salas.filter(Boolean) : [];
  if (lista.length === 0) {
    return { plantas: [], niveles: [], mundo: { ancho: 0, fondo: 0, alto: 0 } };
  }

  const { puestas, pasillos, huella, patio, entrada } = repartirAnillo(lista);
  const soloSala = opciones.soloSala ?? null;
  const plantas = [];

  //  TODO LO QUE ES CIRCULACIÓN, junto: por acá se entra a las salas y por acá
  //  cruzan las figuras de ambiente.
  const circulacion = [...pasillos, patio, entrada].filter(Boolean);

  //  LOS VANOS QUE DAN AL PATIO, para que no se le pongan muebles delante.
  //  Se llena al colocar las salas y se usa al amueblar el patio, mas abajo.
  const vanosAlPatio = [];

  /**
   * El vano de la puerta lateral de una sala, si hay circulación a su
   * izquierda.
   *
   * SE DECIDE POR GEOMETRÍA Y NO POR BANDA. Hoy son las salas de la manzana
   * derecha las que tienen el pasillo contra el muro, pero eso es consecuencia
   * de cómo reparte `anillo.js`, no una ley. Preguntarle al plano —¿hay algo
   * por donde se pase pegado a mi muro izquierdo?— sigue siendo cierto el día
   * que el reparto cambie.
   *
   * A un cuarto del fondo y de 1,8 de ancho, los mismos números que
   * `edificio.js`: centrada queda detrás del puesto principal en casi todas
   * las plantillas, y una puerta tapada por una silla no se lee como puerta.
   */
  /** ¿Hay circulación pegada a este lado de la sala? */
  const daACirculacion = (p, lado) => circulacion.some((c) => {
    if (lado === 'izquierda') {
      return Math.abs(c.x + c.ancho - p.x) < 0.01
        && c.y < p.y + p.fondo && p.y < c.y + c.fondo;
    }
    if (lado === 'derecha') {
      return Math.abs(c.x - (p.x + p.ancho)) < 0.01
        && c.y < p.y + p.fondo && p.y < c.y + c.fondo;
    }
    if (lado === 'frente') {
      return Math.abs(c.y - (p.y + p.fondo)) < 0.01
        && c.x < p.x + p.ancho && p.x < c.x + c.ancho;
    }
    return Math.abs(c.y + c.fondo - p.y) < 0.01
      && c.x < p.x + p.ancho && p.x < c.x + c.ancho;
  });

  /** ¿Hay otra sala pegada a este lado? */
  const salaPegada = (p, lado) => puestas.some((q) => {
    if (q === p) return false;
    if (lado === 'derecha') {
      return Math.abs(q.x - (p.x + p.ancho)) < 0.01
        && q.y < p.y + p.fondo && p.y < q.y + q.fondo;
    }
    return Math.abs(q.y - (p.y + p.fondo)) < 0.01
      && q.x < p.x + p.ancho && p.x < q.x + q.ancho;
  });

  /** Lo que mide un vano de puerta. Una persona pasa; dos no. */
  const ANCHO_DE_VANO = 1.8;

  /**
   * El vano de una puerta en un lado de la sala, corrido al hueco que haya.
   *
   * ARRANCÓ EN «UN CUARTO DEL LADO», copiado de `edificio.js`, y la guarda de
   * `sede.test.js` lo tumbó: en la plantilla de atención el puesto «Atención
   * 1» queda a 1,2 del muro justo donde caía el vano. Una puerta tapada por
   * una silla no se lee como puerta, y encima deja a ese puesto sin salida.
   *
   * Así que el vano se busca, igual que el ancla de los rótulos: se recorre el
   * lado y se elige el tramo más lejano de cualquier puesto pegado a ese muro.
   * No se mueve el escritorio —los puestos salen de lo que declara la
   * empresa— sino la puerta, que es lo que este archivo sí decide.
   *
   * @param largo cuánto mide ese lado, en celdas
   * @param estorbos posición a lo largo del lado de lo que no se puede tapar
   */
  const vanoDe = (largo, estorbos = []) => {
    const margen = 0.6;
    const util = largo - margen * 2 - ANCHO_DE_VANO;
    if (util <= 0) return [margen, largo - margen];
    let mejor = margen;
    let mejorHolgura = -Infinity;
    //  Once posiciones alcanzan: un vano mide 1,8 y los lados miden 9 o 14.
    for (let i = 0; i <= 10; i++) {
      const desde = margen + (i / 10) * util;
      const centro = desde + ANCHO_DE_VANO / 2;
      const holgura = estorbos.length === 0
        ? 0
        : Math.min(...estorbos.map((e) => Math.abs(e - centro)));
      if (holgura > mejorHolgura) {
        mejorHolgura = holgura;
        mejor = desde;
      }
    }
    return [Number(mejor.toFixed(2)), Number((mejor + ANCHO_DE_VANO).toFixed(2))];
  };

  /**
   * Los puestos que están lo bastante cerca de un muro como para estorbar su
   * puerta, proyectados sobre ese muro.
   *
   * @param planta la sala ya compuesta
   * @param lado cuál de los cuatro
   */
  const estorbosDe = (planta, lado) => {
    const CERCA = 2.2;
    const m = planta.mundo;
    return (planta.puestos ?? [])
      .filter((q) => {
        if (lado === 'izquierda') return (q.gx ?? 0) < CERCA;
        if (lado === 'derecha') return m.ancho - (q.gx ?? 0) < CERCA;
        return m.fondo - (q.gy ?? 0) < CERCA;
      })
      .map((q) => (lado === 'frente' ? (q.gx ?? 0) : (q.gy ?? 0)));
  };

  /**
   * EL CERRAMIENTO DE UNA SALA, DEDUCIDO DEL PLANO.
   *
   * Se decide por geometría y no por el nombre del departamento: preguntarle
   * al plano —¿qué tengo pegado a cada lado?— sigue siendo cierto el día que
   * el reparto cambie, y además es la única forma de que valga para una
   * empresa que declare otros departamentos.
   *
   * Las reglas, y cada una tiene su motivo:
   *
   * - Los muros ALTOS de fondo e izquierda ya los dibuja la sala. Llevan vano
   *   sólo si ese lado da a una circulación; contra otra sala sería una puerta
   *   a un escritorio ajeno.
   * - Los dos lados que miran a la cámara llevan PETO, que cierra el recinto
   *   sin tapar a nadie. Ver `ALTURA_DE_ANTEPECHO`.
   * - **Ningún peto donde ya hay otra sala pegada**: ahí está su muro alto, y
   *   dos cerramientos en el mismo borde son la «pared duplicada» que hay que
   *   evitar. Es también lo que hace que una columna de salas se lea como una
   *   manzana maciza y no como una fila de cajas.
   * - Y ningún vano contra el borde del edificio: un hueco que no da a ningún
   *   sitio es un agujero, no una puerta.
   */
  const cerramientoDe = (p, planta) => {
    const ladoIzq = daACirculacion(p, 'izquierda');
    const ladoDer = daACirculacion(p, 'derecha');
    const alFrente = daACirculacion(p, 'frente');
    const petoDerecha = !salaPegada(p, 'derecha');
    const petoFrente = !salaPegada(p, 'frente');
    const con = (lado) => estorbosDe(planta, lado);
    return {
      puertaLateral: ladoIzq ? vanoDe(p.fondo, con('izquierda')) : undefined,
      antepecho: (petoDerecha || petoFrente)
        ? { frente: petoFrente, derecha: petoDerecha }
        : undefined,
      puertaDerecha: petoDerecha && ladoDer ? vanoDe(p.fondo, con('derecha')) : undefined,
      puertaFrente: petoFrente && alFrente ? vanoDe(p.ancho, con('frente')) : undefined
    };
  };

  //  1. EL SUELO DE LA SEDE, bajo todo.
  //
  //     Una sola pieza y no una por sala: en una planta abierta el suelo es
  //     continuo y lo que separa un departamento de otro son sus muros, no un
  //     escalón. Es justo al revés que en el edificio apilado, donde cada sala
  //     llevaba su losa porque entre ellas había aire.
  plantas.push({
    mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: 0.8 },
    origen: { gx: 0, gy: 0, gz: -0.8 },
    nivel: null,
    papel: 'arquitectura',
    pasillo: null,
    mobiliario: [],
    puestos: [],
    arquitectura: {
      tipo: 'basamento',
      ancho: huella.ancho,
      fondo: huella.fondo,
      altura: 0.8
    }
  });

  //  2. LA PLAZA, al frente. Suelo por el que se pasa, sin muros: es por donde
  //     se entra y es lo que hace que la planta se lea como una sede y no como
  //     un almacén de cubículos.
  plantas.push({
    mundo: { ancho: entrada.ancho, fondo: entrada.fondo, alto: 0 },
    origen: { gx: entrada.x, gy: entrada.y, gz: 0 },
    nivel: null,
    papel: 'circulacion',
    pasillo: { desde: 0, hasta: entrada.ancho },
    cartel: null,
    mural: null,
    muros: false,
    losa: true,
    baranda: false,
    //  El mostrador que marca el acceso. No reemplaza a la recepción: esa es
    //  una sala declarada y sigue donde la ponga el reparto.
    mobiliario: mobiliarioDeEntrada(entrada),
    puestos: []
  });

  //  3. Los departamentos, cada uno en su celda y para siempre en la misma.
  const ids = [];
  for (const puesta of puestas) {
    if (soloSala !== null && puesta.sala.id !== soloSala) continue;
    //  LA SALA EN SU TAMANO REAL, pegada a la esquina de su celda.
    //
    //  Se probó estirarla hasta llenar la celda —así compartía muros con la
    //  vecina— y en el navegador se vio por qué está mal: todas las salas
    //  quedaban del mismo tamaño, perdiendo que el NOC es ancho y Dirección
    //  chica, y cada una arrastraba un halo de suelo pelado porque el
    //  mobiliario de una plantilla de 13 × 9 quedaba centrado en una sala de
    //  21 × 13. «Se ve muy estirada», y era verdad.
    //
    //  Pegadas a la esquina y no centradas: así las de una misma columna
    //  alinean su muro izquierdo y las de una misma fila su muro de fondo. Lo
    //  que sobra no queda repartido alrededor de cada sala sino junto, al
    //  frente y a la derecha, y eso se lee como pasillo.
    const planta = plantaDe(puesta.sala, agentes);
    const cierre = cerramientoDe(puesta, { ...planta, mundo: { ...planta.mundo, ancho: puesta.ancho, fondo: puesta.fondo } });
    //  Si este vano da al patio, se anota en coordenadas LOCALES del patio.
    if (patio) {
      if (cierre.puertaDerecha && Math.abs(patio.x - (puesta.x + puesta.ancho)) < 0.01) {
        vanosAlPatio.push({
          lado: 'izquierda',
          desde: puesta.y + cierre.puertaDerecha[0] - patio.y,
          hasta: puesta.y + cierre.puertaDerecha[1] - patio.y
        });
      }
      if (cierre.puertaLateral && Math.abs(patio.x + patio.ancho - puesta.x) < 0.01) {
        vanosAlPatio.push({
          lado: 'derecha',
          desde: puesta.y + cierre.puertaLateral[0] - patio.y,
          hasta: puesta.y + cierre.puertaLateral[1] - patio.y
        });
      }
    }
    //  EL ANCHO SALE DEL REPARTO, NO DE LA PLANTILLA. `anillo.js` ensancha
    //  cada sala hasta llenar su columna para que no quede suelo muerto al
    //  costado; si acá se dibujara con el ancho de la plantilla, ese suelo
    //  volvería a aparecer —y encima la sala ya no tocaría la circulación—.
    //  Y el fondo igual: una columna mas corta que la otra dejaba una franja
    //  muerta al frente del edificio, asi que el sobrante se reparte entre sus
    //  salas.
    plantas.push({
      ...planta,
      mundo: {
        ...planta.mundo,
        ancho: puesta.ancho,
        fondo: puesta.fondo,
        ...(cierre.puertaLateral ? { puertaLateral: cierre.puertaLateral } : {}),
        ...(cierre.antepecho ? { antepecho: cierre.antepecho } : {}),
        ...(cierre.puertaDerecha ? { puertaDerecha: cierre.puertaDerecha } : {}),
        ...(cierre.puertaFrente ? { puertaFrente: cierre.puertaFrente } : {})
      },
      origen: { gx: puesta.x, gy: puesta.y, gz: 0 },
      //  SIN LOSA PROPIA: el suelo ya está, y dos suelos a la misma altura se
      //  solapan de forma indefinida —ahí aparece el parpadeo entre
      //  fotogramas—. Es la misma lección que la fachada a −0,6 en
      //  `edificio.js`.
      losa: false,
      baranda: false,
      rotuloFrontal: puesta.sala.rotulo,
      nivel: puesta.sala.piso ?? null,
      papel: 'sala',
      sala: puesta.sala.id,
      banda: puesta.banda
    });
    ids.push(puesta.sala.id);
  }

  //  4. EL PATIO. Suelo por el que se pasa, sin muros, y AMUEBLADO: un
  //     rectángulo de suelo liso en el medio de la empresa se lee como un
  //     descampado por grande o chico que sea. Lo que lo convierte en patio no
  //     es el tamaño sino que tenga para qué estar. Ver `patio.js`.
  if (patio) {
    plantas.push({
      mundo: { ancho: patio.ancho, fondo: patio.fondo, alto: 0 },
      origen: { gx: patio.x, gy: patio.y, gz: 0 },
      nivel: null,
      papel: 'circulacion',
      pasillo: { desde: 0, hasta: patio.ancho },
      cartel: null,
      mural: null,
      muros: false,
      losa: true,
      baranda: false,
      mobiliario: mobiliarioDePatio(patio, vanosAlPatio),
      puestos: []
    });
  }

  //  4b. LOS PASILLOS entre columnas de una misma manzana. Sin ellos la
  //      columna de atrás no tiene por dónde entrar: su única salida da contra
  //      el muro de la sala de adelante. Van SIN mobiliario —un pasillo de
  //      tres de ancho con un banco deja de ser un pasillo— y como
  //      `circulacion`, así que las figuras de ambiente también los recorren.
  for (const pasillo of pasillos) {
    plantas.push({
      mundo: { ancho: pasillo.ancho, fondo: pasillo.fondo, alto: 0 },
      origen: { gx: pasillo.x, gy: pasillo.y, gz: 0 },
      nivel: null,
      papel: 'circulacion',
      pasillo: { desde: 0, hasta: pasillo.ancho },
      cartel: null,
      mural: null,
      muros: false,
      losa: true,
      baranda: false,
      mobiliario: [],
      puestos: []
    });
  }

  //  5. EL PERÍMETRO: el muro de fondo y los dos costados.
  //
  //     El frente queda ABIERTO, y no por falta de ganas: en esta isometría el
  //     muro del frente estaría entre la cámara y la oficina entera. Es la
  //     misma razón por la que las salas no llevan techo.
  const periferia = (pieza, origen) => plantas.unshift({
    mundo: { ancho: pieza.ancho ?? 0.6, fondo: pieza.fondo ?? 0.6, alto: ALTURA_DE_MURO },
    origen,
    nivel: null,
    papel: 'arquitectura',
    pasillo: null,
    mobiliario: [],
    puestos: [],
    arquitectura: pieza
  });
  periferia(
    { tipo: 'fachada', ancho: huella.ancho, altura: ALTURA_DE_MURO },
    { gx: 0, gy: -0.6, gz: 0 }
  );
  periferia(
    { tipo: 'extremo', fondo: huella.fondo, altura: ALTURA_DE_MURO },
    { gx: -0.6, gy: 0, gz: 0 }
  );
  periferia(
    { tipo: 'extremo', fondo: huella.fondo, altura: ALTURA_DE_MURO },
    { gx: huella.ancho, gy: 0, gz: 0 }
  );

  return {
    plantas,
    //  Un solo nivel, y lo dice con esas palabras: quien navega pregunta por
    //  niveles y tiene que recibir una respuesta honesta, no una lista vacía
    //  que se lea como «no hay datos».
    niveles: [{ nivel: 1, rotulo: 'Planta', declarado: true, gz: 0, salas: ids }],
    mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: ALTURA_DE_MURO }
  };
}

//  Acá vivía `sitioDe`, y no la reemplaza nada: no tenía un solo llamador y
//  llamaba a `repartirPlantaUnica`, que este archivo NO importa. O sea que si
//  alguien la hubiera usado habría reventado con un ReferenceError. Es el
//  mismo caso que `colocarCorte()` unas horas antes: una función que quedó sin
//  llamador al extraer un módulo y que nada señaló. Cuando haga falta llevar la
//  cámara a un departamento, el dato sale de `repartirAnillo`.

export { ENTRADA, PASILLO };
