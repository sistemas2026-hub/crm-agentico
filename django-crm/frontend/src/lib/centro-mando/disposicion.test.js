import { describe, it, expect } from 'vitest';
import {
  anillo,
  radioVerticalMaximo,
  anchoDeEstacion,
  rutaFlujo,
  seSolapan
} from './disposicion.js';

/**
 * Estas pruebas existen por lo que paso el 23/09/2026: el anillo se colocaba
 * con radios a ojo y con ocho agentes las tarjetas se invadian. Cada
 * comprobacion de aqui es una de las formas concretas en que fallo.
 */

describe('el anillo', () => {
  it('reparte parejo, sean dos o doce', () => {
    for (const n of [2, 6, 8, 12]) {
      const p = anillo(n, { cx: 500, cy: 400, rx: 400, ry: 250 });
      expect(p).toHaveLength(n);
      const saltos = p.slice(1).map((q, i) => q.angulo - p[i].angulo);
      for (const s of saltos) expect(s).toBeCloseTo(360 / n, 6);
    }
  });

  it('empieza arriba, para que el primero no quede tapado', () => {
    const [primero] = anillo(4, { cx: 100, cy: 100, rx: 50, ry: 50 });
    expect(primero.y).toBeLessThan(100);
    expect(primero.mitadSuperior).toBe(true);
  });

  it('dice de que mitad es cada estacion: la placa cuelga hacia el lado libre', () => {
    const p = anillo(4, { cx: 0, cy: 0, rx: 10, ry: 10 });
    expect(p.filter((q) => q.mitadSuperior)).toHaveLength(1);
    expect(p.filter((q) => !q.mitadSuperior).length).toBeGreaterThan(0);
  });

  it('con cero estaciones no revienta', () => {
    expect(anillo(0, { cx: 0, cy: 0, rx: 1, ry: 1 })).toEqual([]);
  });
});

describe('las medidas que se calculan en vez de estimarse', () => {
  it('el radio deja sitio para la tarjeta de arriba y la de abajo', () => {
    // 830 de alto con tarjetas de 165: el radio no puede pasar de ~185, que
    // es exactamente el numero al que se llego midiendo.
    const ry = radioVerticalMaximo({ alto: 830, altoTarjeta: 165, separacion: 80 });
    expect(ry).toBeLessThanOrEqual(185);
    expect(830 / 2 - ry - 80 - 165).toBeGreaterThanOrEqual(-1);
  });

  it('con mas alto disponible el anillo se abre', () => {
    const chico = radioVerticalMaximo({ alto: 700, altoTarjeta: 150 });
    const grande = radioVerticalMaximo({ alto: 1000, altoTarjeta: 150 });
    expect(grande).toBeGreaterThan(chico);
  });

  it('nunca devuelve un radio negativo aunque no quepa nada', () => {
    expect(radioVerticalMaximo({ alto: 200, altoTarjeta: 300 })).toBeGreaterThan(0);
  });

  it('la estacion se encoge cuando hay mas agentes', () => {
    const seis = anchoDeEstacion({ n: 6, rx: 450, ry: 250 });
    const doce = anchoDeEstacion({ n: 12, rx: 450, ry: 250 });
    expect(doce).toBeLessThan(seis);
  });

  it('pero nunca por debajo del minimo legible ni por encima del maximo', () => {
    expect(anchoDeEstacion({ n: 40, rx: 450, ry: 250, min: 170 })).toBe(170);
    expect(anchoDeEstacion({ n: 1, rx: 450, ry: 250, max: 320 })).toBe(320);
  });
});

describe('la ruta de un flujo', () => {
  it('arranca en el origen y termina en el destino', () => {
    const d = rutaFlujo({ x: 10, y: 20 }, { x: 110, y: 220 });
    expect(d.startsWith('M 10,20')).toBe(true);
    expect(d.endsWith('110,220')).toBe(true);
  });

  it('sin curvatura es una recta', () => {
    expect(rutaFlujo({ x: 0, y: 0 }, { x: 10, y: 10 }, 0)).toBe('M 0,0 L 10,10');
  });

  it('con curvatura se aparta del segmento', () => {
    const d = rutaFlujo({ x: 0, y: 0 }, { x: 100, y: 0 }, 0.3);
    expect(d).toContain('Q');
    // el punto de control no puede quedar sobre la recta, o no habria curva
    expect(d).not.toContain('Q 50,0');
  });
});

describe('la comprobacion de solapes', () => {
  const caja = (x, y) => ({ x, y, ancho: 100, alto: 50 });

  it('detecta dos cajas encimadas', () => {
    expect(seSolapan(caja(0, 0), caja(50, 20))).toBe(true);
  });

  it('dos cajas separadas no se pisan', () => {
    expect(seSolapan(caja(0, 0), caja(200, 0))).toBe(false);
    expect(seSolapan(caja(0, 0), caja(0, 100))).toBe(false);
  });

  it('tocarse por el borde no cuenta como pisarse', () => {
    expect(seSolapan(caja(0, 0), caja(100, 0))).toBe(false);
  });

  it('el margen tolera un roce de pocos pixeles', () => {
    // Los pods son imagenes con mucho transparente: sus cajas se tocan sin
    // que se vea nada. Medir sin margen daba catorce falsos positivos.
    expect(seSolapan(caja(0, 0), caja(95, 45), 10)).toBe(false);
    expect(seSolapan(caja(0, 0), caja(50, 20), 10)).toBe(true);
  });
});
