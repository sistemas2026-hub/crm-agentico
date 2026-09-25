import { describe, it, expect } from 'vitest';
import {
  anillo,
  angulosPorArco,
  radiosDelAnillo,
  dentroDelLienzo,
  radioVerticalMaximo,
  anchoDeEstacion,
  rutaFlujo,
  seSolapan,
  seSolapanEnElAnillo
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

/**
 * Lo que sigue nace del 24/09/2026, al pasar de tarjetas rectangulares a
 * discos en anillo: el reparto por angulos iguales, que parecia obvio, ponia
 * cuatro pares de vecinos uno encima del otro.
 */

describe('el reparto por arco', () => {
  /** distancia entre vecinos consecutivos sobre la elipse */
  const separaciones = (angulos, rx, ry) =>
    angulos.map((a, i) => {
      const b = angulos[(i + 1) % angulos.length];
      return Math.hypot(rx * Math.cos(b) - rx * Math.cos(a), ry * Math.sin(b) - ry * Math.sin(a));
    });

  it('deja a todos los vecinos a la misma distancia real', () => {
    const rx = 430;
    const ry = 165;
    const seps = separaciones(angulosPorArco(8, rx, ry), rx, ry);
    const menor = Math.min(...seps);
    const mayor = Math.max(...seps);
    // el reparto por angulo, sobre esta misma elipse, da una diferencia > 2x
    expect(mayor / menor).toBeLessThan(1.1);
  });

  it('quita los solapes que el reparto por angulo producia', () => {
    // La medida que importa no es la distancia entre centros sino si las
    // CAJAS se pisan: dos piezas a 171 px en diagonal se solapan igual, con
    // 120 de ese salto en x y 122 en y. Medirlo por distancia fue mi primer
    // error al escribir esta prueba.
    const rx = 430;
    const ry = 165;
    const W = 156;
    const H = 152; // disco + nombre + tarea, medidos en el navegador
    const cajas = (/** @type {number[]} */ angulos) =>
      angulos.map((a) => ({ x: rx * Math.cos(a) - W / 2, y: ry * Math.sin(a) - H / 2, ancho: W, alto: H }));
    const solapes = (/** @type {any[]} */ c) => {
      let n = 0;
      for (let i = 0; i < c.length; i++) for (let j = i + 1; j < c.length; j++) if (seSolapan(c[i], c[j])) n++;
      return n;
    };
    const porAngulo = Array.from({ length: 8 }, (_, i) => -Math.PI / 2 + (2 * Math.PI * i) / 8);
    expect(solapes(cajas(porAngulo))).toBe(4); // los cuatro que se vieron en pantalla
    expect(solapes(cajas(angulosPorArco(8, rx, ry)))).toBe(0);
  });

  it('empieza arriba y da tantos angulos como piezas', () => {
    for (const n of [1, 3, 8, 14]) {
      const a = angulosPorArco(n, 300, 200);
      expect(a).toHaveLength(n);
      expect(Math.sin(a[0])).toBeCloseTo(-1, 2);
    }
    expect(angulosPorArco(0, 10, 10)).toEqual([]);
  });

  it('en un circulo coincide con el reparto por angulo', () => {
    const a = angulosPorArco(6, 200, 200);
    a.forEach((v, i) => expect(v).toBeCloseTo(-Math.PI / 2 + (2 * Math.PI * i) / 6, 2));
  });
});

describe('los radios del anillo', () => {
  it('usan el espacio que hay, no un porcentaje', () => {
    const { rx, ry, cabe } = radiosDelAnillo({ ancho: 1029, alto: 515, anchoPieza: 156, altoPieza: 152 });
    expect(rx + 156 / 2 + 16).toBeCloseTo(1029 / 2, 0);
    expect(ry + 152 / 2 + 16).toBeCloseTo(515 / 2, 0);
    expect(cabe).toBe(true);
  });

  it('descuentan el desfase: lo que se coloca es el disco, no la caja', () => {
    const sin = radiosDelAnillo({ ancho: 1000, alto: 500, anchoPieza: 156, altoPieza: 138 });
    const con = radiosDelAnillo({ ancho: 1000, alto: 500, anchoPieza: 156, altoPieza: 138, desfase: 17 });
    expect(sin.ry - con.ry).toBe(17);
    expect(con.rx).toBe(sin.rx); // el desfase es vertical: el ancho no cambia
  });

  it('avisan cuando no cabe, en vez de pintar el disco sobre el centro', () => {
    // el caso real medido a 1366x768 antes de achicar el disco: hacen falta
    // 51,5 + 71,5 + 12 = 135 de radio y el alto solo daba 119
    const r = radiosDelAnillo({
      ancho: 1010, alto: 442, anchoPieza: 156, altoPieza: 138,
      desfase: 17, radioPieza: 51.5, radioCentro: 71.5
    });
    expect(r.cabe).toBe(false);

    // con el disco y el nucleo mas chicos, y algo mas de alto, si cabe
    const ok = radiosDelAnillo({
      ancho: 1010, alto: 484, anchoPieza: 156, altoPieza: 123,
      desfase: 17, radioPieza: 44, radioCentro: 62
    });
    expect(ok.cabe).toBe(true);
    expect(ok.ry).toBeGreaterThanOrEqual(44 + 62 + 12);
  });

  it('el minimo deja la PIEZA ENTERA fuera del nodo central, no solo el disco', () => {
    const { rx, ry } = radiosDelAnillo({
      ancho: 300, alto: 200, anchoPieza: 260, altoPieza: 180, radioPieza: 44, radioCentro: 62
    });
    expect(rx).toBeGreaterThanOrEqual(260 / 2 + 62 + 12);
    expect(ry).toBeGreaterThanOrEqual(180 / 2 + 62 + 12);
  });

  it('no dice que cabe cuando el texto terminaria encima del centro', () => {
    // el caso medido: 439x500 daba cabe con el disco como referencia, y en
    // pantalla quedaban dos discos dentro del nucleo y cinco piezas fuera
    const r = radiosDelAnillo({
      ancho: 439, alto: 500, anchoPieza: 156, altoPieza: 140,
      desfase: 24.4, radioPieza: 45.6, radioCentro: 62
    });
    expect(r.cabe).toBe(false);
  });
});

describe('acotar al lienzo', () => {
  it('mete la pieza que se sale, y no mueve la que ya cabe', () => {
    const lienzo = { ancho: 1000, alto: 600 };
    const pieza = { ancho: 200, alto: 100 };
    expect(dentroDelLienzo({ x: 500, y: 300 }, pieza, lienzo)).toEqual({ x: 500, y: 300 });
    expect(dentroDelLienzo({ x: 10, y: 5 }, pieza, lienzo)).toEqual({ x: 116, y: 66 });
    expect(dentroDelLienzo({ x: 990, y: 595 }, pieza, lienzo)).toEqual({ x: 884, y: 534 });
  });

  it('no invierte los limites cuando la pieza es mas grande que el lienzo', () => {
    const p = dentroDelLienzo({ x: 50, y: 50 }, { ancho: 400, alto: 400 }, { ancho: 300, alto: 300 });
    expect(Number.isFinite(p.x)).toBe(true);
    expect(Number.isFinite(p.y)).toBe(true);
  });
});

describe('si las piezas caben en el anillo', () => {
  const pieza = { anchoPieza: 156, altoPieza: 140 };
  const anillo = (n, rx, ry) => ({ angulos: angulosPorArco(n, rx, ry), rx, ry, ...pieza });

  it('con los ocho agentes de Rapilink, en el lienzo real, no se pisan', () => {
    expect(seSolapanEnElAnillo(anillo(8, 428, 189))).toBe(false);
  });

  it('con once en el MISMO anillo, si: el radio alcanza y las piezas no', () => {
    // medido en el navegador el 24/09/2026: mismo lienzo, mismo radio, y los
    // vecinos empiezan a montarse a partir de once
    expect(seSolapanEnElAnillo(anillo(11, 428, 189))).toBe(true);
    expect(seSolapanEnElAnillo(anillo(14, 428, 189))).toBe(true);
  });

  it('los mismos once caben si el anillo es mas grande', () => {
    expect(seSolapanEnElAnillo(anillo(11, 700, 420))).toBe(false);
  });

  it('uno solo nunca se pisa consigo mismo', () => {
    expect(seSolapanEnElAnillo(anillo(1, 300, 200))).toBe(false);
  });
});
