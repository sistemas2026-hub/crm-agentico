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

  const { puestas, huella, patio, entrada } = repartirAnillo(lista);
  const soloSala = opciones.soloSala ?? null;
  const plantas = [];

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
    mobiliario: [],
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
    plantas.push({
      ...planta,
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

  //  4. EL PATIO, si la rejilla llegó hasta sus celdas. Suelo por el que se
  //     pasa, sin muros: es el hueco alrededor del cual se ordena la sede.
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

/** Dónde está un departamento en la planta, para llevar la cámara. */
export function sitioDe(salas, id) {
  const { puestas } = repartirPlantaUnica(Array.isArray(salas) ? salas : []);
  const p = puestas.find((x) => x.sala.id === id);
  if (!p) return null;
  return { gx: p.x + p.ancho / 2, gy: p.y + p.fondo / 2, ancho: p.ancho, fondo: p.fondo };
}

export { ENTRADA, PASILLO };
