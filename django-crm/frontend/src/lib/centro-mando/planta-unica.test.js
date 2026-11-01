import { describe, it, expect } from 'vitest';
import { salasDe } from './departamentos.js';
import { repartirPiso } from './three/distribucion.js';
import {
  CELDA_MAXIMA, PLAZA, celdaDe, celdaPara, plazaPara, repartirPlantaUnica
} from './planta-unica.js';

/**
 * LA PLANTA ÚNICA, Y LA PROPIEDAD QUE TIENE QUE CUMPLIR.
 *
 * El 01/11/2026 se fijaron dos reglas de producto: todos los departamentos van
 * en una sola planta —se navega trasladándose, no cambiando de piso— y una
 * empresa **crea más agentes a medida que crece**.
 *
 * De la segunda sale la afirmación que este archivo mide, y que no es
 * estética: **agregar un departamento no puede mover a los que ya estaban.**
 * Una oficina virtual sirve porque uno se acuerda de dónde están las cosas; la
 * que se reacomoda sola deja de ser un lugar. El reparto anterior movía 19 de
 * 23 salas al pasar de 23 a 24 departamentos, y eso está medido acá abajo como
 * control: sin él, una prueba que diga «cero se movieron» podría estar
 * midiendo una función que no hace nada.
 */

const sala = (id, ancho = 12, fondo = 9) => ({
  id,
  rotulo: id,
  planta: { mundo: { ancho, fondo } }
});

const empresaDe = (n) => Array.from({ length: n }, (_, i) => sala('d' + i));

/** ¿Cuántas de las `n` primeras salas cambiaron de sitio al agregar una más? */
function seMueven(reparto, n) {
  const antes = reparto(empresaDe(n)).puestas;
  const despues = reparto(empresaDe(n + 1)).puestas;
  let movidas = 0;
  for (let i = 0; i < n; i++) {
    if (antes[i].x !== despues[i].x || antes[i].y !== despues[i].y) movidas++;
  }
  return movidas;
}

describe('crecer no mueve la oficina', () => {
  it('agregar un departamento no mueve NINGUNO de los que estaban', () => {
    //  LA PRUEBA QUE IMPORTA DE TODO EL ARCHIVO.
    for (let n = 1; n <= 40; n++) {
      expect(seMueven(repartirPlantaUnica, n), `con ${n} departamentos`).toBe(0);
    }
  });

  it('y el reparto anterior SÍ las movía: la prueba de arriba mide algo', () => {
    //  El control. Sin esto, `seMueven` podría devolver 0 por un error —dos
    //  listas iguales, un índice mal— y la afirmación de arriba sería un
    //  adorno. Estos tres números son los que motivaron el cambio.
    expect(seMueven(repartirPiso, 7)).toBeGreaterThan(0);
    expect(seMueven(repartirPiso, 14)).toBeGreaterThan(0);
    expect(seMueven(repartirPiso, 23)).toBeGreaterThan(0);
  });

  it('la celda de una sala no depende de cuántas salas haya', () => {
    //  Es la misma propiedad mirada desde el otro lado: dada la celda de la
    //  empresa, `celdaDe(i)` es pura. La celda hay que pasarla: con la mayor
    //  posible por omisión, la secuencia es otra —la forma de la celda es
    //  justo lo que decide si conviene crecer a lo ancho o a lo hondo—.
    const celda = celdaPara(empresaDe(50));
    for (const i of [0, 1, 2, 5, 11, 23, 39]) {
      const c = celdaDe(i, celda);
      expect(celdaDe(i, celda)).toEqual(c);
      const enUnaGrande = repartirPlantaUnica(empresaDe(50)).puestas[i];
      expect({ columna: enUnaGrande.columna, fila: enUnaGrande.fila }).toEqual(c);
    }
  });

  it('agrandar una sala DENTRO de su celda no mueve a nadie', () => {
    //  El otro modo de crecer: el departamento suma agentes y su sala se hace
    //  más grande. Mientras siga entrando en la celda, no corre a nadie.
    const chicas = empresaDe(9);
    const conUnaMayor = empresaDe(9);
    const celda = celdaPara(chicas);
    conUnaMayor[3] = sala('d3', celda.ancho - 6, celda.fondo - 6);
    const a = repartirPlantaUnica(chicas).puestas;
    const b = repartirPlantaUnica(conUnaMayor).puestas;
    for (let i = 0; i < 9; i++) {
      if (i === 3) continue;
      expect([b[i].x, b[i].y], `d${i} se movió`).toEqual([a[i].x, a[i].y]);
    }
  });

  it('y pasarse de la celda SÍ recoloca la planta, que es el precio', () => {
    //  Dicho sin suavizar, porque es la contrapartida de que la planta se vea
    //  como una oficina y no como chozas en un descampado: la celda sale de la
    //  sala mayor de la empresa, así que una sala que se pasa del múltiplo
    //  agranda la celda y recoloca todo.
    //
    //  Esta prueba no está para defender ese comportamiento: está para que el
    //  día que alguien lo cambie sepa qué estaba cambiando. Lo que NO puede
    //  volver a pasar —y está medido arriba— es que mover a todos ocurra al
    //  AGREGAR un departamento, que era la queja.
    const antes = empresaDe(9);
    const despues = empresaDe(9);
    despues[3] = sala('d3', 33.8, 15.4);
    expect(celdaPara(despues).ancho).toBeGreaterThan(celdaPara(antes).ancho);
    const a = repartirPlantaUnica(antes).puestas;
    const b = repartirPlantaUnica(despues).puestas;
    const movidas = a.filter((p, i) => p.x !== b[i].x || p.y !== b[i].y).length;
    expect(movidas).toBeGreaterThan(0);
  });
});

describe('la planta es una sede y no una franja', () => {
  it('la esbeltez se queda por debajo de 2 en cualquier tamaño', () => {
    //  El 31/10/2026 el diseño no se aprobó con esbeltez 4,85: «demasiado
    //  largo, estrecho y lineal».
    for (const n of [1, 3, 5, 8, 12, 20, 30, 50, 80]) {
      const { huella } = repartirPlantaUnica(empresaDe(n));
      const esbeltez = huella.ancho / huella.fondo;
      expect(esbeltez, `${n} departamentos: ${huella.ancho}×${huella.fondo}`).toBeLessThan(2);
      expect(esbeltez, `${n} departamentos: ${huella.ancho}×${huella.fondo}`).toBeGreaterThan(0.6);
    }
  });

  it('ninguna sala se superpone con otra', () => {
    for (const n of [1, 2, 5, 9, 17, 30, 50]) {
      const p = repartirPlantaUnica(empresaDe(n)).puestas;
      for (const a of p) {
        for (const b of p) {
          if (a === b) continue;
          const cruza =
            a.x < b.x + b.ancho && b.x < a.x + a.ancho &&
            a.y < b.y + b.fondo && b.y < a.y + a.fondo;
          expect(cruza, `${a.sala.id} se mete en ${b.sala.id}`).toBe(false);
        }
      }
    }
  });

  it('ni siquiera con las salas más grandes que el catálogo sabe construir', () => {
    //  La celda es constante y vale porque es mayor que la sala mayor. Si
    //  alguien agranda una plantilla por encima de la celda, esto se pone en
    //  rojo antes de que dos departamentos se monten en el navegador.
    const grandes = Array.from({ length: 12 }, (_, i) => sala('g' + i, 33.8, 15.4));
    const p = repartirPlantaUnica(grandes).puestas;
    for (const a of p) {
      for (const b of p) {
        if (a === b) continue;
        const cruza =
          a.x < b.x + b.ancho && b.x < a.x + a.ancho &&
          a.y < b.y + b.fondo && b.y < a.y + a.fondo;
        expect(cruza, `${a.sala.id} y ${b.sala.id}`).toBe(false);
      }
    }
  });

  it('toda sala cabe dentro de su celda, también la mayor posible', () => {
    //  33,8 × 15,4 es `tecnica_25`, la mayor que `plantillaPara()` construye.
    const grande = [sala('g', 33.8, 15.4)];
    expect(celdaPara(grande).ancho).toBeGreaterThan(33.8);
    expect(celdaPara(grande).fondo).toBeGreaterThan(15.4);
    expect(CELDA_MAXIMA.ancho).toBeGreaterThan(33.8);
  });

  it('y la celda se ajusta a la empresa en vez de ser siempre la mayor', () => {
    //  Lo que arregló que la planta pareciera chozas sueltas: con salas de
    //  12 × 9, la celda ya no mide 38 × 18.
    const celda = celdaPara(empresaDe(8));
    expect(celda.ancho).toBeLessThan(CELDA_MAXIMA.ancho);
    expect(celda.ancho).toBeGreaterThan(12);
  });
});

describe('la plaza, por donde se entra', () => {
  it('va AL FRENTE, que en esta proyección es el gy mayor', () => {
    //  La primera versión la puso en `gy = 0` creyendo que ahí estaba el
    //  frente. En el navegador salió una losa pálida enorme detrás de todo,
    //  que no se leía como una entrada sino como un muro. En esta isometría
    //  `gy` crece hacia quien mira.
    const { plaza, puestas, huella } = repartirPlantaUnica(empresaDe(8));
    const laMasAlFrente = Math.max(...puestas.map((p) => p.y + p.fondo));
    expect(plaza.y).toBeGreaterThanOrEqual(laMasAlFrente);
    expect(plaza.ancho).toBe(huella.ancho);
    expect(plaza.fondo).toBe(plazaPara(huella.ancho));
  });

  it('y ninguna sala se le mete adentro', () => {
    for (const n of [1, 5, 20]) {
      const { plaza, puestas } = repartirPlantaUnica(empresaDe(n));
      for (const p of puestas) {
        expect(p.y + p.fondo, `${p.sala.id} invade la plaza`).toBeLessThanOrEqual(plaza.y);
      }
    }
  });
});

describe('la planta dice la verdad sobre la empresa', () => {
  it('están todas las salas declaradas, y ninguna inventada', () => {
    const puestas = repartirPlantaUnica(empresaDe(11)).puestas;
    expect(puestas.map((p) => p.sala.id)).toEqual(empresaDe(11).map((s) => s.id));
  });

  it('una empresa sin estructura no produce planta', () => {
    expect(repartirPlantaUnica([]).puestas).toEqual([]);
    expect(repartirPlantaUnica(null).puestas).toEqual([]);
  });

  it('funciona con la empresa real, por el mismo camino que la pantalla', () => {
    const org = {
      pisos: [{ nivel: 1, rotulo: 'Único' }],
      departamentos: [
        { id: 'noc', rotulo: 'NOC', piso: 1, plantilla: 'tecnica', ocupaciones: [] },
        { id: 'atencion', rotulo: 'Atención', piso: 1, plantilla: 'atencion', ocupaciones: [] },
        { id: 'finanzas', rotulo: 'Finanzas', piso: 1, plantilla: 'expedientes', ocupaciones: [] }
      ],
      espacios: [
        { id: 'recepcion', rotulo: 'Recepción', piso: 1, plantilla: 'generica', ocupaciones: [] }
      ]
    };
    const { puestas, huella } = repartirPlantaUnica(salasDe(org));
    expect(puestas).toHaveLength(4);
    expect(huella.ancho).toBeGreaterThan(0);
  });
});
