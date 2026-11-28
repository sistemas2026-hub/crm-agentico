import { describe, it, expect } from 'vitest';
import { VINETA, alfaDeVineta } from './texturas';

/**
 * LA VIÑETA, QUE ESTABA APAGANDO LAS ORILLAS DE LA OFICINA.
 *
 * Esto no se probaba porque `texturas.ts` genera imágenes con un lienzo, y un
 * lienzo no existe en este arnés. Pero la CURVA sí es aritmética, y era donde
 * estaba el defecto: medido sobre una captura del 02/11/2026,
 *
 *     dentro del edificio, 48% de los pixeles por debajo de media escala
 *     por tercios del ancho:  izquierda 110 · centro 134 · derecha 110
 *
 * seis de cada diez pixeles de las orillas caían por debajo de 128, contra
 * menos de cuatro en el centro. Con once departamentos repartidos por toda la
 * planta, eso es mobiliario que no se ve.
 *
 * El suelo medía 168 de 255, así que el problema NO era la iluminación de la
 * sala: era esta capa encima.
 */

describe('la viñeta oscurece el borde sin apagarlo', () => {
  it('el centro no se toca', () => {
    //  Una viñeta que resta luz en el centro es un filtro, no una viñeta.
    for (const p of [0, 0.2, 0.4, 0.6, VINETA.desde]) {
      expect(alfaDeVineta(p), `a ${p} del centro`).toBe(0);
    }
  });

  it('no pasa de la mitad de negro ni en la esquina', () => {
    //  ESTA ES LA AFIRMACIÓN QUE HABRÍA CAZADO EL DEFECTO. El valor anterior
    //  era 0,82: cuatro quintas partes de negro sobre la esquina del
    //  encuadre, que es donde caen Recepción y la Sala de Reuniones.
    expect(alfaDeVineta(1)).toBeLessThanOrEqual(0.5);
    expect(alfaDeVineta(1)).toBe(VINETA.techo);
  });

  it('y a media rampa oscurece poco', () => {
    //  El tramo que de verdad importa: la zona entre el centro y la esquina,
    //  que es la mayor parte del borde visible. Antes, a 0,85 del centro ya
    //  restaba un 25%.
    const aMedias = alfaDeVineta(VINETA.desde + (1 - VINETA.desde) / 2);
    expect(aMedias, `a media rampa resta ${(aMedias * 100).toFixed(0)}%`)
      .toBeLessThan(0.15);
  });

  it('crece sin saltos desde donde arranca', () => {
    //  Un escalón en la rampa se ve como un anillo alrededor de la oficina.
    let previo = -1;
    for (let i = 0; i <= 40; i++) {
      const a = alfaDeVineta(i / 40);
      expect(a).toBeGreaterThanOrEqual(previo);
      previo = a;
    }
  });

  it('fuera de rango no devuelve basura', () => {
    expect(alfaDeVineta(-1)).toBe(0);
    expect(alfaDeVineta(5)).toBe(VINETA.techo);
    expect(Number.isFinite(alfaDeVineta(0.9))).toBe(true);
  });
});
