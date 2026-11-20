import { describe, it, expect } from 'vitest';
import {
  ALTURA_UNIDAD,
  BALDOSA,
  aPantalla,
  aRejilla,
  extensionDelMundo,
  profundidad,
  rombo
} from './isometria';

/**
 * Lo que se fija acá es que la proyección sea invertible y que la altura reste.
 *
 * Los dos errores que esto caza son de los que no fallan: con la altura sumando,
 * el mobiliario se hunde en el piso y parece un problema de orden de pintado;
 * con la inversa mal, el puntero selecciona la celda de al lado y no hay forma
 * de saber si el error está en la proyección o en la cámara.
 */

describe('la proyección y su inversa cierran', () => {
  it('ida y vuelta devuelve la misma celda', () => {
    for (const [gx, gy] of [
      [0, 0],
      [3, 7],
      [13.5, 9.25],
      [-2, 4]
    ]) {
      const p = aPantalla(gx, gy, 0);
      const r = aRejilla(p.x, p.y);
      expect(r.x).toBeCloseTo(gx, 6);
      expect(r.y).toBeCloseTo(gy, 6);
    }
  });

  it('el origen de la rejilla es el origen de pantalla', () => {
    expect(aPantalla(0, 0, 0)).toEqual({ x: 0, y: 0 });
  });

  it('la relación es 2:1, que es lo que evita el serrucho', () => {
    expect(BALDOSA.ancho).toBe(BALDOSA.alto * 2);
  });
});

describe('la altura resta, no suma', () => {
  it('un objeto alto se dibuja MÁS ARRIBA', () => {
    const suelo = aPantalla(5, 5, 0);
    const alto = aPantalla(5, 5, 2);
    expect(alto.y).toBeLessThan(suelo.y);
    expect(suelo.y - alto.y).toBeCloseTo(2 * ALTURA_UNIDAD, 6);
  });

  it('la altura no mueve la posición horizontal', () => {
    expect(aPantalla(4, 2, 3).x).toBe(aPantalla(4, 2, 0).x);
  });
});

describe('profundidad', () => {
  it('lo que está más cerca de la cámara tiene más profundidad', () => {
    expect(profundidad(1, 1)).toBeLessThan(profundidad(5, 5));
    expect(profundidad(0, 3)).toBe(profundidad(3, 0));
  });

  it('la altura desempata, y pesa muy poco', () => {
    // Con el mismo (gx, gy), lo más alto se pinta después. Si pesara mucho, una
    // pared alta del fondo taparía el mobiliario de delante.
    expect(profundidad(2, 2, 3)).toBeGreaterThan(profundidad(2, 2, 0));
    expect(profundidad(2, 2, 3)).toBeLessThan(profundidad(2, 3, 0));
  });
});

describe('el rombo de una baldosa', () => {
  it('son cuatro vértices, no tres', () => {
    // El cuarto es el que se olvida, y entonces la baldosa se ve como un
    // triángulo y parece un problema de la textura.
    expect(rombo(0, 0)).toHaveLength(4);
  });

  it('el rombo ocupa exactamente una baldosa', () => {
    const v = rombo(3, 4);
    const xs = v.map((p) => p.x);
    const ys = v.map((p) => p.y);
    expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo(BALDOSA.ancho, 6);
    expect(Math.max(...ys) - Math.min(...ys)).toBeCloseTo(BALDOSA.alto, 6);
  });
});

describe('la extensión del mundo', () => {
  const mundo = { ancho: 14, fondo: 10, alto: 4 };
  const ext = extensionDelMundo(mundo);

  it('incluye la altura de las paredes', () => {
    // Si solo midiera el suelo, al encuadrar el remate de los muros quedaría
    // cortado por arriba: se nota al entrar, no al escribir el código.
    const soloSuelo = Math.abs(aPantalla(mundo.ancho, mundo.fondo, 0).y - aPantalla(0, 0, 0).y);
    expect(ext.alto).toBeGreaterThan(soloSuelo);
  });

  it('el centro está dentro de la extensión', () => {
    expect(ext.centro.x).toBeGreaterThanOrEqual(ext.minX);
    expect(ext.centro.x).toBeLessThanOrEqual(ext.maxX);
    expect(ext.centro.y).toBeGreaterThanOrEqual(ext.minY);
    expect(ext.centro.y).toBeLessThanOrEqual(ext.maxY);
  });

  it('el ancho cubre las dos esquinas laterales', () => {
    const derecha = aPantalla(mundo.ancho, 0, 0).x;
    const izquierda = aPantalla(0, mundo.fondo, 0).x;
    expect(ext.ancho).toBeCloseTo(derecha - izquierda, 6);
  });
});
