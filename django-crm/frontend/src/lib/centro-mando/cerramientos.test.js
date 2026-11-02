import { describe, it, expect } from 'vitest';
import { sedeDe } from './sede.js';
import { salasDe } from './departamentos.js';
import PORDEFECTO from './__fixtures__/organizacion-por-defecto.json';
import { celdaDe, conectividad, rejillaDe, transitable } from './navegacion.js';

/**
 * LA MATRIZ DE LAS ONCE SALAS: dato, dibujo y ruta tienen que decir lo mismo.
 *
 * Nace de una pregunta que una captura no puede contestar: cuando una oficina
 * «parece» no tener puerta, ¿falta la puerta en los datos, o existe y el
 * renderizador no la dibuja? Son dos defectos distintos y se arreglan en
 * sitios distintos.
 *
 * Por eso cada sala se mide en TRES sitios:
 *
 *     DATO     lo que la planta declara (`mundo.puertaX`)
 *     DIBUJO   si `oficina.ts` llega a pintar ese vano, con sus condiciones
 *     RUTA     si la rejilla deja pasar por ahí
 *
 * Tres columnas que coinciden es un sistema coherente. Dos de tres es un
 * defecto, y cuál falla dice dónde está.
 *
 * Y SE MIDE SOBRE LA EMPRESA DEL PILOTO, no sobre una sintética. Las guardas
 * de `navegacion.test.js` y `sede.test.js` arman su propia empresa con las
 * plantillas en orden, y eso les sirve para barrer tamaños — pero el defecto
 * que encontró esta matriz **sólo aparece en el reparto real**: el macetero de
 * una esquina de la franja de entrada caía delante del vano de Recepción, y en
 * la empresa sintética esa esquina queda en otro sitio.
 */

const SEDE = sedeDe(salasDe(PORDEFECTO), []);
const REJILLA = rejillaDe(SEDE);
const SALAS = SEDE.plantas.filter((p) => p.papel === 'sala');
const CIRCULACION = SEDE.plantas
  .filter((p) => p.papel === 'circulacion')
  .map((p) => ({ x: p.origen.gx, y: p.origen.gy, ancho: p.mundo.ancho, fondo: p.mundo.fondo }));

const LADOS = ['fondo', 'izquierda', 'frente', 'derecha'];

/** El vano declarado en un lado, si lo hay. */
const vanoDeclarado = (m, lado) => (
  lado === 'fondo' ? m.puerta
    : lado === 'izquierda' ? m.puertaLateral
      : lado === 'frente' ? m.puertaFrente
        : m.puertaDerecha) ?? null;

/**
 * ¿Llega la escena a pintar ese vano?
 *
 * Se replican acá las condiciones de `construirMuros` y `construirAntepecho`:
 * los muros altos de fondo e izquierda pintan su vano siempre que exista; los
 * dos del peto SÓLO si ese lado lleva peto. Esa condición de más es justamente
 * la que puede dejar un vano declarado sin dibujar.
 */
const seDibuja = (m, lado) => {
  const v = vanoDeclarado(m, lado);
  if (!v) return false;
  if (lado === 'frente') return Boolean(m.antepecho?.frente);
  if (lado === 'derecha') return Boolean(m.antepecho?.derecha);
  return true;
};

/** ¿Está libre la celda de justo afuera de ese vano? */
const sePasa = (p, lado) => {
  const v = vanoDeclarado(p.mundo, lado);
  if (!v) return false;
  const o = p.origen;
  const m = p.mundo;
  const medio = (v[0] + v[1]) / 2;
  const punto = lado === 'izquierda' ? [o.gx - 0.3, o.gy + medio]
    : lado === 'derecha' ? [o.gx + m.ancho + 0.3, o.gy + medio]
      : lado === 'frente' ? [o.gx + medio, o.gy + m.fondo + 0.3]
        : [o.gx + medio, o.gy - 0.3];
  const c = celdaDe(punto[0], punto[1]);
  return transitable(REJILLA, c.cx, c.cy);
};

/** ¿Hay otra sala pegada a este lado? */
const vecina = (p, lado) => SALAS.some((q) => {
  if (q === p) return false;
  const o = p.origen; const m = p.mundo;
  const oq = q.origen; const mq = q.mundo;
  if (lado === 'derecha') {
    return Math.abs(oq.gx - (o.gx + m.ancho)) < 0.01
      && oq.gy < o.gy + m.fondo && o.gy < oq.gy + mq.fondo;
  }
  return Math.abs(oq.gy - (o.gy + m.fondo)) < 0.01
    && oq.gx < o.gx + m.ancho && o.gx < oq.gx + mq.ancho;
});

describe('la matriz de las once salas', () => {
  it('hay once salas que auditar (si no, la matriz no prueba nada)', () => {
    //  Una matriz que recorre una lista vacía pasa siempre.
    expect(SALAS.length).toBe(11);
    expect(REJILLA.destinos.size).toBeGreaterThanOrEqual(30);
  });

  it('ninguna sala tiene un lado abierto al vacío', () => {
    for (const p of SALAS) {
      const m = p.mundo;
      //  Fondo e izquierda llevan muro alto siempre; los otros dos, peto —
      //  salvo que haya otra sala pegada, que ya los cierra con el suyo.
      expect(Boolean(m.antepecho?.frente) || vecina(p, 'frente'),
        `${p.sala}: abierta por el frente`).toBe(true);
      expect(Boolean(m.antepecho?.derecha) || vecina(p, 'derecha'),
        `${p.sala}: abierta por la derecha`).toBe(true);
    }
  });

  it('todo vano declarado se dibuja', () => {
    //  EL PRIMERO DE LOS TRES DESACUERDOS POSIBLES: la planta dice que hay
    //  puerta y la escena no la pinta porque falta la condición del peto.
    for (const p of SALAS) {
      for (const lado of LADOS) {
        if (!vanoDeclarado(p.mundo, lado)) continue;
        expect(seDibuja(p.mundo, lado),
          `${p.sala}: vano declarado en «${lado}» que NO se dibuja`).toBe(true);
      }
    }
  });

  it('por todo vano dibujado se pasa', () => {
    //  EL SEGUNDO, y es el que encontró la puerta de Recepción tapada por un
    //  macetero de la franja de entrada. La puerta estaba dibujada y la celda
    //  de justo afuera, ocupada.
    for (const p of SALAS) {
      for (const lado of LADOS) {
        if (!seDibuja(p.mundo, lado)) continue;
        expect(sePasa(p, lado),
          `${p.sala}: vano dibujado en «${lado}» por el que NO se pasa`).toBe(true);
      }
    }
  });

  it('y no se pasa por donde no hay vano dibujado', () => {
    //  EL TERCERO: un agujero en la rejilla sin puerta a la vista. Ahí un
    //  personaje atraviesa lo que parece una pared.
    for (const p of SALAS) {
      for (const lado of LADOS) {
        if (!vanoDeclarado(p.mundo, lado)) continue;
        if (seDibuja(p.mundo, lado)) continue;
        expect(sePasa(p, lado),
          `${p.sala}: se pasa por «${lado}» sin vano dibujado`).toBe(false);
      }
    }
  });

  it('cada sala tiene al menos una puerta', () => {
    for (const p of SALAS) {
      const cuantas = LADOS.filter((l) => seDibuja(p.mundo, l)).length;
      expect(cuantas, `${p.sala} no tiene ninguna puerta dibujada`).toBeGreaterThan(0);
    }
  });

  it('y todos sus puestos se alcanzan desde la circulación', () => {
    const { aislados } = conectividad(REJILLA, CIRCULACION);
    expect(aislados, `sin ruta: ${aislados.join(', ')}`).toEqual([]);
  });
});
