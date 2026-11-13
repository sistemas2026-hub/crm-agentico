/**
 * LA OPCIÓN B: el edificio compacto, DIBUJADO CON PIXIJS.
 *
 * Por qué existe este archivo
 * ---------------------------
 * El 01/11/2026 el spike de Three.js demostró que la planta compacta se puede
 * componer —esbeltez 1,05 contra 4,85— y de ahí salió una pregunta que el
 * spike NO contesta: *¿hacía falta cambiar de motor para tener esa planta?*
 *
 * Yo había contestado que sí, y lo había contestado mal. Dije que dos filas de
 * salas exigirían 28,7 unidades de aire entre losas —una torre de 86 para 40 de
 * planta— y eso era una estimación, no una medición. Medido con la misma
 * inversión de la proyección que usa `edificio.test.js`, con la losa por sala
 * que este motor ya usa, **a la altura de piso actual no se tapa ni un puesto**
 * (`edificio-compacto.test.js`). La planta compacta cabe en PixiJS.
 *
 * Lo que sí es verdad, y es lo que esta comparación aporta
 * -------------------------------------------------------
 * Que quepa no quiere decir que esté garantizada. La visibilidad en 2.5D
 * depende de la ALTURA DE PISO, y no monótonamente: con la empresa del piloto
 * se ve entera a 15, se rompe entre 16 y 29 —dos a cuatro puestos tapados— y
 * vuelve a verse a partir de 30. Funciona porque los pasillos del piso de
 * arriba caen justo donde están los escritorios del de abajo, y eso es una
 * coincidencia de la rejilla, no una propiedad del diseño: cambiar el pasillo,
 * el fondo de una plantilla o agregar una sala la mueve. El síntoma, cuando se
 * rompe, es un puesto que nadie ve, sin error y sin aviso.
 *
 * En tres dimensiones reales esa pregunta no existe: el buffer de profundidad
 * decide por geometría y la altura de piso es libre.
 *
 * Qué NO construye, a propósito
 * -----------------------------
 * Ni fachada, ni extremo acristalado, ni el canto de losa con el nombre al
 * frente. `edificio.js` los coloca con una aritmética que supone UNA fila
 * —`frente`, `sostiene`, `anchoDeNivel`— y rehacerla para una huella en
 * rejilla es el trabajo que esta comparación tiene que MEDIR, no el que tiene
 * que hacer antes de que se decida el motor. Es el experimento mínimo que pide
 * la comparación, y ese hueco es parte del resultado.
 *
 * `edificio.js` no se modificó para esto: sólo se exportaron dos funciones que
 * ya existían. La opción A queda intacta y recuperable, que es la restricción.
 */

import { plantaDe } from './departamentos.js';
import { ALTURA_DE_PISO, circulacion, nucleo } from './edificio.js';
import { repartirPiso, NUCLEO } from './three/distribucion.js';

/**
 * El edificio compacto de una empresa, con el contrato de `edificioDe`.
 *
 * Mismos tres valores de vuelta —`plantas`, `niveles`, `mundo`— porque la
 * pantalla y `montar.ts` consumen eso y no tienen por qué saber qué
 * distribución están dibujando. Es lo que permite comparar A y B con la misma
 * escena, los mismos personajes y la misma ficha de puesto.
 *
 * @param {any[]} salas las salas de la empresa, ya compuestas
 * @param {any[]} agentes el inventario del motor
 * @param {any[]} pisos los niveles declarados
 * `alturaDePiso` no está para configurarla: está para que la prueba pueda
 * BARRERLA. Lo que hay que poder afirmar de esta distribución no es que a 15 se
 * vea —eso es un punto— sino que a otras alturas no, que es la fragilidad.
 *
 * @param {{ soloNivel?: number|null, losaCorrida?: boolean,
 *           alturaDePiso?: number }} [opciones]
 */
export function edificioCompactoPixi(salas, agentes, pisos, opciones = {}) {
  const lista = Array.isArray(salas) ? salas : [];
  const niveles = Array.isArray(pisos) ? pisos : [];
  const soloNivel = opciones.soloNivel ?? null;
  const losaCorrida = opciones.losaCorrida === true;
  const altura = opciones.alturaDePiso ?? ALTURA_DE_PISO;

  if (lista.length === 0 || niveles.length === 0) {
    return { plantas: [], niveles: [], mundo: { ancho: 0, fondo: 0, alto: 0 } };
  }

  const nivelMinimo = Math.min(...niveles.map((p) => p.nivel));

  //  LA HUELLA ES COMPARTIDA, y es la diferencia de fondo con `edificio.js`.
  //
  //  Allá cada nivel mide lo suyo y el escalonado dice cuántas salas tiene cada
  //  piso: información verdadera. Acá el edificio tiene un volumen único y un
  //  piso con menos salas tiene más suelo libre: también es verdadero, y se
  //  parece a la referencia. Las dos cosas no se pueden tener a la vez y por eso
  //  esto es una comparación y no una mejora.
  const repartos = niveles.map((piso) => ({
    piso,
    ...repartirPiso(piso.salas ?? lista.filter((s) => s.piso === piso.nivel))
  }));
  const huella = repartos.reduce(
    (acc, r) => ({
      ancho: Math.max(acc.ancho, r.huella.ancho),
      fondo: Math.max(acc.fondo, r.huella.fondo)
    }),
    { ancho: 0, fondo: 0 }
  );

  const plantas = [];
  const detalle = [];
  let gzMasAlto = -Infinity;

  for (const r of repartos) {
    if (soloNivel !== null && r.piso.nivel !== soloNivel) continue;

    //  Aislado, el nivel baja al suelo: lo mismo que hace `edificio.js`, y por
    //  el mismo motivo —un piso solo flotando a dos pisos de altura deja la
    //  cámara encuadrando vacío—.
    const gz = soloNivel !== null ? 0 : (r.piso.nivel - nivelMinimo) * altura;
    const acento = r.puestas[0]?.sala?.planta?.acento;
    const encima = niveles
      .map((p) => p.nivel)
      .filter((n) => n > r.piso.nivel)
      .sort((a, b) => a - b)[0];
    const ids = [];

    //  1. El núcleo, en la esquina, apilado en la misma huella en todos los
    //     niveles. Igual que en A: ahí es donde no se tapa a sí mismo.
    plantas.push({
      ...nucleo(acento, soloNivel !== null ? 5 : altura),
      origen: { gx: 0, gy: 0, gz },
      nivel: r.piso.nivel,
      papel: 'nucleo'
    });

    //  2. El suelo del piso.
    //
    //     DOS ESTRATEGIAS, Y LA DIFERENCIA ES MEDIBLE. Una losa corrida bajo
    //     toda la huella es lo que hace que un piso se lea como un piso y no
    //     como bandejas sueltas; también es lo que tapa el piso de abajo: con
    //     ella la altura de piso mínima sube de 15 a 38, o sea una torre de
    //     114 unidades para 40 de planta. Por defecto va la losa por sala, que
    //     es la que esta altura permite, y la corrida queda tras una opción
    //     para poder MIRAR el defecto en vez de describirlo.
    if (losaCorrida) {
      plantas.push({
        ...circulacion(huella.ancho, acento,
                       encima === undefined ? 0 : huella.ancho,
                       soloNivel !== null ? 2.5 : undefined),
        mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: 0 },
        pasillo: { desde: 0, hasta: huella.ancho },
        origen: { gx: 0, gy: 0, gz },
        nivel: r.piso.nivel,
        papel: 'circulacion'
      });
    }

    //  3. Las salas, en rejilla: varias filas y varias columnas.
    for (const puesta of r.puestas) {
      const planta = plantaDe(puesta.sala, agentes);
      plantas.push({
        ...planta,
        origen: { gx: puesta.x, gy: puesta.y, gz },
        //  Sin losa propia cuando hay losa corrida: dos suelos a la misma
        //  profundidad se solapan de forma indefinida y ahí aparece el
        //  parpadeo entre fotogramas. Es la misma lección que la fachada a
        //  −0,6 en `edificio.js`.
        losa: !losaCorrida,
        baranda: !losaCorrida,
        rotuloFrontal: puesta.sala.rotulo,
        nivel: r.piso.nivel,
        papel: 'sala',
        sala: puesta.sala.id,
        //  De qué fila y columna salió. No lo usa el dibujo: lo usa la prueba,
        //  que es la que tiene que poder afirmar «hay más de una fila» sin
        //  reconstruirlo comparando coordenadas.
        celda: { fila: puesta.fila, columna: puesta.columna }
      });
      ids.push(puesta.sala.id);
    }

    gzMasAlto = Math.max(gzMasAlto, gz);
    detalle.push({
      nivel: r.piso.nivel,
      rotulo: String(r.piso.rotulo ?? ''),
      declarado: r.piso.declarado !== false,
      gz,
      salas: ids
    });
  }

  if (plantas.length === 0) {
    return { plantas: [], niveles: [], mundo: { ancho: 0, fondo: 0, alto: 0 } };
  }

  //  4. El remate: basamento abajo y cubierta arriba, los dos sobre la huella
  //     compartida. Son las dos piezas que hacen que el volumen termine en algo
  //     y no en el aire, y en una huella única son triviales — es el único
  //     sitio donde compartir huella sale más barato que escalonar.
  plantas.unshift({
    mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: 1.4 },
    origen: { gx: 0, gy: 0, gz: -1.4 },
    nivel: null,
    papel: 'arquitectura',
    pasillo: null,
    mobiliario: [],
    puestos: [],
    arquitectura: { tipo: 'basamento', ancho: huella.ancho, fondo: huella.fondo, altura: 1.4 }
  });
  //  LA CUBIERTA ES EL LÍMITE DE ESTA OPCIÓN, Y ACÁ SE VE ENTERO.
  //
  //  Medido: en el edificio completo, una cubierta sobre la huella de 39 × 39
  //  tapa NUEVE puestos de los pisos de arriba —y es la ÚNICA pieza que tapa
  //  algo: las salas, el núcleo y el basamento no tapan ni uno—. En la
  //  distribución lineal no pasa porque esa huella tiene 18 celdas de fondo, no
  //  39: lo que cambió no es el remate, es la profundidad que tiene que cruzar
  //  la proyección.
  //
  //  Mirando un piso SOLO no hay nada que rematar, así que no se dibuja, y eso
  //  no es un parche: es lo mismo que hace `edificio.js` cortando la fachada a
  //  5,6 y las columnas a 2,5 cuando se aísla un nivel. Un remate sobre el
  //  vacío tapa la planta que se está mirando y no dice nada.
  //
  //  En el edificio completo NO hay salida barata: o no lleva cubierta —y un
  //  edificio sin remate no se lee como un edificio—, o la altura de piso sube
  //  a lo que la proyección exija. Las dos cosas están medidas en
  //  `edificio-compacto.test.js`, y es la diferencia de fondo con tres
  //  dimensiones reales, donde la cubierta se recorta o se apaga y lo de abajo
  //  sigue siendo correcto sin recalcular nada.
  if (soloNivel === null && opciones.cubierta !== false) {
    plantas.push({
      mundo: { ancho: huella.ancho, fondo: huella.fondo, alto: 0.5 },
      origen: { gx: 0, gy: 0, gz: gzMasAlto + altura },
      nivel: null,
      papel: 'arquitectura',
      pasillo: null,
      mobiliario: [],
      puestos: [],
      arquitectura: { tipo: 'cubierta', ancho: huella.ancho, fondo: huella.fondo, altura: 0.5 }
    });
  }

  return {
    plantas,
    niveles: detalle,
    mundo: {
      ancho: Math.max(huella.ancho, NUCLEO.ancho),
      fondo: Math.max(huella.fondo, NUCLEO.fondo),
      alto: gzMasAlto + altura
    }
  };
}
