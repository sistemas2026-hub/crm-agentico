import { describe, it, expect } from 'vitest';
import {
  CUANTAS, DENSIDAD, OFICIOS, PASO, PAUSA,
  avanzar, azar, cuantasFiguras, poblar, puntoEn
} from './ambiente.js';

/**
 * LAS FIGURAS DE AMBIENTE, Y LA LÍNEA QUE NO PUEDEN CRUZAR.
 *
 * El permiso para que haya gente caminando vino con una condición escrita:
 * procedencia `ambiente`, y **nunca registrarse como actividad operativa
 * real**. Lo que estas pruebas miden no es que las figuras existan —eso se ve
 * mirando— sino que no puedan confundirse con un agente ni decir nada sobre la
 * empresa:
 *
 * - no salen de los datos de la empresa, sino del tamaño de la circulación;
 * - no pisan donde hay escritorios;
 * - y la escena se ve igual en dos cargas seguidas, que es lo que permite
 *   comparar una captura contra otra.
 */

const zona = (x, y, ancho, fondo) => ({ x, y, ancho, fondo });
const PATIO = zona(20, 0, 16, 30);
const ENTRADA = zona(20, 30, 16, 8);

describe('cuántas figuras hay, y de dónde sale ese número', () => {
  it('sale del tamaño de la circulación y de nada más', () => {
    expect(cuantasFiguras(DENSIDAD * 3)).toBe(3);
    expect(cuantasFiguras(DENSIDAD * 5)).toBe(5);
  });

  it('nunca menos de una ni más del tope', () => {
    //  Cero figuras en una sede chica la deja muerta; veinte en una grande son
    //  una multitud que tapa la oficina.
    expect(cuantasFiguras(0)).toBe(CUANTAS.minimo);
    expect(cuantasFiguras(10)).toBe(CUANTAS.minimo);
    expect(cuantasFiguras(DENSIDAD * 500)).toBe(CUANTAS.maximo);
    expect(cuantasFiguras(-5)).toBe(CUANTAS.minimo);
  });

  it('NO depende de cuántos agentes tenga la empresa', () => {
    //  LA PRUEBA QUE IMPORTA DE ESTE BLOQUE. Si el número saliera de los
    //  datos, la escena estaría diciendo algo sobre la empresa con figuras que
    //  no representan a nadie, y quien la mire leería una señal donde no la
    //  hay. `cuantasFiguras` recibe un área y nada más: no hay forma de
    //  pasarle un dato de la empresa aunque se quiera.
    expect(cuantasFiguras.length).toBe(1);
    expect(cuantasFiguras(DENSIDAD * 2)).toBe(cuantasFiguras(DENSIDAD * 2));
  });

  it('una sede sin circulación no tiene a nadie caminando', () => {
    expect(poblar([])).toEqual([]);
    expect(poblar(null)).toEqual([]);
    //  Una zona de dos celdas no es un pasillo: es una junta entre salas.
    expect(poblar([zona(0, 0, 1, 1)])).toEqual([]);
  });
});

describe('dónde caminan', () => {
  it('todas arrancan dentro de una zona de circulación', () => {
    for (const f of poblar([PATIO, ENTRADA])) {
      const dentro = [PATIO, ENTRADA].some(
        (z) => f.x >= z.x && f.x <= z.x + z.ancho && f.y >= z.y && f.y <= z.y + z.fondo);
      expect(dentro, `${f.id} nace fuera de la circulación`).toBe(true);
    }
  });

  it('y su destino también', () => {
    for (const f of poblar([PATIO, ENTRADA])) {
      const dentro = [PATIO, ENTRADA].some(
        (z) => f.destino.x >= z.x && f.destino.x <= z.x + z.ancho &&
               f.destino.y >= z.y && f.destino.y <= z.y + z.fondo);
      expect(dentro, `${f.id} va hacia fuera de la circulación`).toBe(true);
    }
  });

  it('nunca se meten donde hay escritorios, ni después de mil pasos', () => {
    //  LA LÍNEA QUE NO SE CRUZA. Una figura dentro de una sala estaría
    //  pisando puestos declarados, y además se dibujaría atravesando una
    //  pared: el mundo ordena por `zIndex` y una figura a ese nivel va entera
    //  delante o detrás de la sala, nunca entre sus muebles.
    let figuras = poblar([PATIO, ENTRADA]);
    for (let t = 0; t < 1000; t++) {
      figuras = figuras.map((f) => avanzar(f, 0.1, [PATIO, ENTRADA]));
      for (const f of figuras) {
        const dentro = [PATIO, ENTRADA].some(
          (z) => f.x >= z.x - 0.1 && f.x <= z.x + z.ancho + 0.1 &&
                 f.y >= z.y - 0.1 && f.y <= z.y + z.fondo + 0.1);
        expect(dentro, `${f.id} se salió en el paso ${t}: ${f.x.toFixed(1)},${f.y.toFixed(1)}`)
          .toBe(true);
      }
    }
  });

  it('el punto elegido deja margen con los bordes', () => {
    //  Pegada al borde, la figura se dibuja medio cuerpo dentro de un muro.
    for (let s = 0; s < 40; s++) {
      const p = puntoEn(PATIO, s);
      expect(p.x).toBeGreaterThan(PATIO.x);
      expect(p.x).toBeLessThan(PATIO.x + PATIO.ancho);
      expect(p.y).toBeGreaterThan(PATIO.y);
      expect(p.y).toBeLessThan(PATIO.y + PATIO.fondo);
    }
  });
});

describe('cómo se mueven', () => {
  it('caminan hacia su destino y llegan', () => {
    let f = { ...poblar([PATIO])[0], espera: 0 };
    const lejosAlPrincipio = Math.hypot(f.destino.x - f.x, f.destino.y - f.y);
    for (let i = 0; i < 200 && !f.espera; i++) f = avanzar(f, 0.1, [PATIO]);
    expect(lejosAlPrincipio).toBeGreaterThan(0.5);
    expect(f.espera).toBeGreaterThan(0);
  });

  it('no caminan más rápido de lo declarado', () => {
    const antes = { ...poblar([PATIO])[0], espera: 0 };
    const despues = avanzar(antes, 1, [PATIO]);
    expect(Math.hypot(despues.x - antes.x, despues.y - antes.y)).toBeLessThan(PASO + 0.01);
  });

  it('se paran un rato al llegar: no patrullan en círculos', () => {
    let f = { ...poblar([PATIO])[0], espera: 0 };
    for (let i = 0; i < 300 && f.espera <= 0; i++) f = avanzar(f, 0.1, [PATIO]);
    expect(f.espera).toBeGreaterThanOrEqual(PAUSA.minima);
    expect(f.espera).toBeLessThanOrEqual(PAUSA.maxima);
  });

  it('mientras esperan no se mueven, y dicen que no están andando', () => {
    const quieta = { ...poblar([PATIO])[0], espera: 2 };
    const d = avanzar(quieta, 0.5, [PATIO]);
    expect([d.x, d.y]).toEqual([quieta.x, quieta.y]);
    expect(d.andando).toBe(false);
  });

  it('no mutan la figura que reciben', () => {
    //  La escena guarda la anterior para interpolar; mutarla la dejaría
    //  comparándose consigo misma y quieta.
    const f = { ...poblar([PATIO])[0], espera: 0 };
    const copia = { ...f };
    avanzar(f, 0.5, [PATIO]);
    expect(f).toEqual(copia);
  });

  it('un dt de cero o basura no las teletransporta', () => {
    const f = { ...poblar([PATIO])[0], espera: 0 };
    for (const dt of [0, -3, NaN, undefined]) {
      const d = avanzar(f, dt, [PATIO]);
      expect(Math.hypot(d.x - f.x, d.y - f.y)).toBeLessThan(0.001);
    }
  });
});

describe('la sede se ve igual en dos cargas seguidas', () => {
  it('poblar dos veces da exactamente lo mismo', () => {
    //  Con `Math.random()` dos capturas del mismo estado saldrían distintas y
    //  no habría forma de comparar una contra otra, que es como se verifica
    //  todo lo demás acá.
    expect(poblar([PATIO, ENTRADA])).toEqual(poblar([PATIO, ENTRADA]));
  });

  it('y el azar estable da siempre el mismo número para la misma semilla', () => {
    expect(azar(7)).toBe(azar(7));
    expect(azar(7)).not.toBe(azar(8));
    for (let s = 0; s < 50; s++) {
      expect(azar(s)).toBeGreaterThanOrEqual(0);
      expect(azar(s)).toBeLessThan(1);
    }
  });

  it('no todas arrancan a la vez: no son un desfile', () => {
    const esperas = new Set(poblar([PATIO, ENTRADA]).map((f) => f.espera.toFixed(3)));
    expect(esperas.size).toBeGreaterThan(1);
  });
});

describe('no son agentes, y no pueden parecerlo', () => {
  it('ninguna figura trae nombre, puesto ni agente', () => {
    //  Lo que separa una figura de ambiente de un empleado inventado es
    //  exactamente esto: no hay a quién atribuirla.
    for (const f of poblar([PATIO, ENTRADA])) {
      expect(f.nombre).toBeUndefined();
      expect(f.agente).toBeUndefined();
      expect(f.puesto).toBeUndefined();
      expect(f.persona).toBeUndefined();
    }
  });

  it('su oficio es una etiqueta de dibujo y no un rol de la empresa', () => {
    for (const f of poblar([PATIO, ENTRADA])) {
      expect(OFICIOS).toContain(f.oficio);
    }
  });
});
