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
import { PLAZA, repartirPlantaUnica } from './planta-unica.js';

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

  const { puestas, huella, plaza } = repartirPlantaUnica(lista);
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
    mundo: { ancho: plaza.ancho, fondo: plaza.fondo, alto: 0 },
    origen: { gx: plaza.x, gy: plaza.y, gz: 0 },
    nivel: null,
    papel: 'circulacion',
    pasillo: { desde: 0, hasta: plaza.ancho },
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
      celda: { fila: puesta.fila, columna: puesta.columna }
    });
    ids.push(puesta.sala.id);
  }

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

export { PLAZA };
