import { describe, it, expect } from 'vitest';
import { sedeDe } from './sede.js';
import { PLANTILLAS } from './plantillas.js';

/**
 * LA SEDE MONTADA, Y LA PUERTA QUE NADIE COMPROBABA.
 *
 * Este archivo nace de un agujero medido en mi propio trabajo. `anillo.test.js`
 * afirma que **toda sala da a una circulación**, y pasó en verde mientras
 * borraba la puerta entera:
 *
 *     con `puertaLateralDe` devolviendo siempre `undefined`:
 *       anillo.test.js  ->  21 verdes, 0 rojas
 *       la sede         ->  0 puertas, 6 salas con MURO CIEGO contra el patio
 *
 * Esa guarda mide ADYACENCIA —que la sala comparta un borde con el patio— y no
 * APERTURA. Es exactamente lo que CLAUDE.md §6 llama «una prueba que dice que
 * algo existe no prueba que funcione», y la escribí citando esa misma regla.
 *
 * Lo que se mide acá es el efecto: que se pueda entrar.
 */

const SALAS = [
  'operaciones', 'tecnica', 'atencion', 'comercial',
  'expedientes', 'reuniones', 'operaciones', 'atencion',
  'expedientes', 'reuniones', 'atencion'
].map((plantilla, i) => ({
  id: `d${i}`,
  rotulo: `Departamento ${i}`,
  tipo: 'departamento',
  piso: 1,
  plantilla,
  planta: { ...PLANTILLAS[plantilla], acento: PLANTILLAS[plantilla].acento }
}));

const salasDe = (n) => SALAS.slice(0, n);

/** Las plantas de sala, con su origen y su mundo ya resuelto. */
const cuartos = (sede) => sede.plantas.filter((p) => p.papel === 'sala');
const circulaciones = (sede) => sede.plantas
  .filter((p) => p.papel === 'circulacion')
  .map((p) => ({
    x: p.origen.gx, y: p.origen.gy, ancho: p.mundo.ancho, fondo: p.mundo.fondo
  }));

/**
 * Por dónde se entra de verdad a una sala.
 *
 * Una sala dibuja DOS muros: el de fondo (`gy = 0`) y el lateral (`gx = 0`).
 * Los otros dos lados están abiertos hacia la cámara. Entonces se entra por:
 *
 * - el lado derecho (`gx = ancho`) o el frontal (`gy = fondo`), que no tienen
 *   muro, si del otro lado hay circulación; o
 * - un vano en uno de los dos muros que sí se dibujan.
 */
function aberturas(planta, circ) {
  const o = planta.origen;
  const caja = { x: o.gx, y: o.gy, ancho: planta.mundo.ancho, fondo: planta.mundo.fondo };
  const pegada = (lado) => circ.some((c) => {
    if (lado === 'derecha') {
      return Math.abs(c.x - (caja.x + caja.ancho)) < 0.01
        && c.y < caja.y + caja.fondo && caja.y < c.y + c.fondo;
    }
    if (lado === 'izquierda') {
      return Math.abs(c.x + c.ancho - caja.x) < 0.01
        && c.y < caja.y + caja.fondo && caja.y < c.y + c.fondo;
    }
    if (lado === 'frente') {
      return Math.abs(c.y - (caja.y + caja.fondo)) < 0.01
        && c.x < caja.x + caja.ancho && caja.x < c.x + c.ancho;
    }
    return Math.abs(c.y + c.fondo - caja.y) < 0.01
      && c.x < caja.x + caja.ancho && caja.x < c.x + c.ancho;
  });

  const salida = [];
  //  Lados ABIERTOS: no hay muro que cruzar.
  if (pegada('derecha')) salida.push('lado derecho abierto');
  if (pegada('frente')) salida.push('frente abierto');
  //  Lados con MURO: hace falta un vano.
  if (pegada('izquierda') && planta.mundo.puertaLateral) salida.push('puerta lateral');
  if (pegada('fondo') && planta.mundo.puerta) salida.push('puerta de fondo');
  return salida;
}

describe('a toda sala se puede entrar DE VERDAD', () => {
  it('cada sala tiene al menos un lado abierto o un vano hacia la circulación', () => {
    //  LA PRUEBA QUE FALTABA. Si `puertaLateralDe` deja de poner el vano, esta
    //  se pone en rojo nombrando las salas que quedaron encerradas — que es lo
    //  que la guarda de adyacencia no podía hacer.
    for (const n of [1, 2, 3, 5, 8, 11]) {
      const sede = sedeDe(salasDe(n), []);
      const circ = circulaciones(sede);
      for (const planta of cuartos(sede)) {
        const vias = aberturas(planta, circ);
        expect(vias.length, `${planta.sala} (empresa de ${n}) queda encerrada`)
          .toBeGreaterThan(0);
      }
    }
  });

  it('una sala con la circulación contra el muro recibe su vano', () => {
    //  La mitad de la sede tiene el patio del lado del muro lateral y no del
    //  lado abierto. Sin vano, esas salas tienen frente a la circulación y
    //  aun así no se entra: la adyacencia se cumple y la puerta no existe.
    const sede = sedeDe(salasDe(11), []);
    const circ = circulaciones(sede);
    const conMuroAlPatio = cuartos(sede).filter((p) => {
      const o = p.origen;
      return circ.some((c) => Math.abs(c.x + c.ancho - o.gx) < 0.01
        && c.y < o.gy + p.mundo.fondo && o.gy < c.y + c.fondo);
    });
    expect(conMuroAlPatio.length, 'ninguna sala tiene el muro contra la circulación')
      .toBeGreaterThan(0);
    for (const p of conMuroAlPatio) {
      expect(p.mundo.puertaLateral, `${p.sala} tiene muro ciego contra la circulación`)
        .toBeTruthy();
    }
  });

  it('el vano cae dentro del muro y no lo parte en dos trozos inútiles', () => {
    const sede = sedeDe(salasDe(11), []);
    for (const p of cuartos(sede)) {
      const v = p.mundo.puertaLateral;
      if (!v) continue;
      expect(v[0]).toBeGreaterThan(0);
      expect(v[1]).toBeLessThan(p.mundo.fondo);
      expect(v[1] - v[0], `${p.sala}: vano de ${(v[1] - v[0]).toFixed(1)}`)
        .toBeGreaterThan(1.2);
    }
  });

  it('una sala mirada sola NO lleva puerta', () => {
    //  Un hueco que no da a ningún sitio es un agujero, no una puerta. Con una
    //  sola sala no hay nada contra su muro lateral.
    const sede = sedeDe(salasDe(1), []);
    expect(cuartos(sede)[0].mundo.puertaLateral).toBeUndefined();
  });
});

describe('la sede devuelve el mismo contrato que el edificio apilado', () => {
  it('trae plantas, niveles y mundo', () => {
    const sede = sedeDe(salasDe(11), []);
    expect(Array.isArray(sede.plantas)).toBe(true);
    expect(sede.niveles).toHaveLength(1);
    expect(sede.niveles[0].salas).toHaveLength(11);
    expect(sede.mundo.ancho).toBeGreaterThan(0);
    expect(sede.mundo.fondo).toBeGreaterThan(0);
  });

  it('una empresa sin salas no revienta y no inventa un edificio', () => {
    const vacia = sedeDe([], []);
    expect(vacia.plantas).toEqual([]);
    expect(vacia.niveles).toEqual([]);
    expect(vacia.mundo).toEqual({ ancho: 0, fondo: 0, alto: 0 });
  });

  it('ninguna sala lleva losa propia', () => {
    //  El suelo de la sede es una sola pieza. Dos suelos a la misma altura se
    //  solapan de forma indefinida, y ahí aparece el parpadeo entre fotogramas.
    for (const p of cuartos(sedeDe(salasDe(11), []))) {
      expect(p.losa, `${p.sala} trae losa`).toBe(false);
    }
  });

  it('el patio y los pasillos no traen puestos', () => {
    //  Una circulación con un puesto sería un escritorio en medio del paso, y
    //  además un puesto que nadie declaró.
    for (const p of sedeDe(salasDe(11), []).plantas) {
      if (p.papel !== 'circulacion') continue;
      expect(p.puestos).toEqual([]);
    }
  });
});

describe('el mobiliario del patio llega a la escena', () => {
  it('el patio sale amueblado y los pasillos no', () => {
    //  Un pasillo de tres de ancho con un banco deja de ser un pasillo.
    const sede = sedeDe(salasDe(11), []);
    const circ = sede.plantas.filter((p) => p.papel === 'circulacion');
    const patio = circ.find((p) => p.mundo.fondo > 20);
    expect(patio, 'no hay patio').toBeTruthy();
    expect(patio.mobiliario.length, 'el patio salió pelado').toBeGreaterThan(4);
  });

  it('la entrada lleva su mostrador', () => {
    const sede = sedeDe(salasDe(11), []);
    const entrada = sede.plantas
      .filter((p) => p.papel === 'circulacion')
      .find((p) => p.mundo.fondo <= 20 && p.mobiliario.length > 0);
    expect(entrada, 'no hay entrada amueblada').toBeTruthy();
    expect(entrada.mobiliario.some((m) => m.tipo === 'mostrador')).toBe(true);
  });
});
