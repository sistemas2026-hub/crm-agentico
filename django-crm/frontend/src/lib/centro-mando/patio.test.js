import { describe, it, expect } from 'vitest';
import { MARGEN_DE_PASO, MINIMO, ORILLA, mobiliarioDeEntrada, mobiliarioDePatio } from './patio.js';
import { poblar, avanzar } from './ambiente.js';

/**
 * EL PATIO AMUEBLADO, Y LO ÚNICO QUE PUEDE ROMPER.
 *
 * Lo que vale la pena medir acá no es que haya muebles —eso se ve mirando—
 * sino las dos cosas que no se ven y arruinan la escena:
 *
 * - que una pieza caiga donde caminan las figuras de ambiente, porque se las
 *   vería atravesando un banco;
 * - que el patio diga algo sobre la empresa, cuando es parte del edificio.
 */

const patio = (ancho, fondo) => ({ x: 0, y: 0, ancho, fondo });

describe('nada se planta donde se camina', () => {
  it('ninguna pieza de suelo cae en la banda por la que cruzan las figuras', () => {
    //  LA PRUEBA QUE IMPORTA. `ambiente.js` mantiene a las figuras a
    //  `MARGEN_DE_PASO` de los bordes; el mobiliario se apoya por fuera de esa
    //  banda. Son dos módulos que no se importan entre sí, así que si alguien
    //  mueve uno de los dos números esto se pone en rojo.
    for (const [ancho, fondo] of [[14, 10], [16, 40], [20, 28], [14, 67], [9, 9]]) {
      for (const p of mobiliarioDePatio(patio(ancho, fondo))) {
        if (p.tipo === 'luminaria') continue; // va en el techo
        const enLaBanda = p.gx > MARGEN_DE_PASO && p.gx < ancho - MARGEN_DE_PASO
          && p.gy > MARGEN_DE_PASO && p.gy < fondo - MARGEN_DE_PASO;
        expect(enLaBanda, `${p.tipo} en (${p.gx}, ${p.gy}) de un patio ${ancho}x${fondo}`)
          .toBe(false);
      }
    }
  });

  it('y las figuras, caminando mil pasos, no pisan ninguna', () => {
    //  La misma afirmación desde el otro lado: en vez de confiar en los dos
    //  números, se camina de verdad y se mide la distancia.
    const zona = { x: 0, y: 0, ancho: 16, fondo: 40 };
    const suelo = mobiliarioDePatio(zona).filter((p) => p.tipo !== 'luminaria');
    let figuras = poblar([zona]);
    let masCerca = Infinity;
    for (let t = 0; t < 1000; t++) {
      figuras = figuras.map((f) => avanzar(f, 0.1, [zona]));
      for (const f of figuras) {
        for (const p of suelo) {
          masCerca = Math.min(masCerca, Math.hypot(f.x - p.gx, f.y - p.gy));
        }
      }
    }
    expect(masCerca, `una figura pasó a ${masCerca.toFixed(2)} de un mueble`)
      .toBeGreaterThan(0.2);
  });

  it('el centro del patio queda libre de punta a punta', () => {
    const suelo = mobiliarioDePatio(patio(16, 40)).filter((p) => p.tipo !== 'luminaria');
    for (const p of suelo) {
      const alBorde = Math.min(p.gx, 16 - p.gx);
      expect(alBorde, `${p.tipo} a ${alBorde} del borde`).toBeLessThan(16 / 2 - 1);
    }
  });
});

describe('el patio no dice nada sobre la empresa', () => {
  it('lo que lleva sale solo de su tamaño', () => {
    //  `mobiliarioDePatio` recibe un rectángulo y nada más: no hay forma de
    //  pasarle un agente, un departamento ni un contador aunque se quiera.
    expect(mobiliarioDePatio.length).toBe(1);
    expect(mobiliarioDePatio(patio(16, 40))).toEqual(mobiliarioDePatio(patio(16, 40)));
  });

  it('ninguna pieza trae nombre, agente ni puesto', () => {
    for (const p of [...mobiliarioDePatio(patio(16, 40)), ...mobiliarioDeEntrada(patio(16, 8))]) {
      expect(p.nombre).toBeUndefined();
      expect(p.agente).toBeUndefined();
      expect(p.puesto).toBeUndefined();
      expect(typeof p.tipo).toBe('string');
    }
  });
});

describe('crece y se achica con el patio', () => {
  it('un patio más hondo lleva más piezas', () => {
    const corto = mobiliarioDePatio(patio(16, 12)).length;
    const largo = mobiliarioDePatio(patio(16, 48)).length;
    expect(largo).toBeGreaterThan(corto);
  });

  it('un patio demasiado chico se queda vacío en vez de amontonar', () => {
    //  Meterle un banco y una mesa a un patio de 6 × 6 lo deja intransitable,
    //  y un patio por el que no se puede pasar no es un patio.
    expect(mobiliarioDePatio(patio(MINIMO.ancho - 1, 20))).toEqual([]);
    expect(mobiliarioDePatio(patio(20, MINIMO.fondo - 1))).toEqual([]);
    expect(mobiliarioDePatio(null)).toEqual([]);
  });

  it('dos piezas nunca quedan en el mismo sitio', () => {
    for (const [ancho, fondo] of [[14, 10], [16, 40], [20, 28], [14, 67], [40, 12]]) {
      const piezas = mobiliarioDePatio(patio(ancho, fondo));
      for (let i = 0; i < piezas.length; i++) {
        for (let j = i + 1; j < piezas.length; j++) {
          const a = piezas[i];
          const b = piezas[j];
          if (a.tipo === 'luminaria' || b.tipo === 'luminaria') continue;
          expect(Math.hypot(a.gx - b.gx, a.gy - b.gy),
            `${a.tipo} y ${b.tipo} encimados en ${ancho}x${fondo}`).toBeGreaterThan(1.2);
        }
      }
    }
  });
});

describe('la entrada marca el acceso', () => {
  it('el mostrador va contra el borde de adentro, no contra el frente', () => {
    //  Apoyado al frente taparía la oficina entera: en esta isometría el frente
    //  está entre la cámara y todo lo demás.
    const piezas = mobiliarioDeEntrada({ ancho: 16, fondo: 8 });
    const mostrador = piezas.find((p) => p.tipo === 'mostrador');
    expect(mostrador).toBeTruthy();
    expect(mostrador.gy).toBe(ORILLA);
    expect(mostrador.largo).toBeGreaterThan(1);
  });

  it('una entrada chica no lleva mostrador', () => {
    expect(mobiliarioDeEntrada({ ancho: 6, fondo: 8 })).toEqual([]);
    expect(mobiliarioDeEntrada({ ancho: 16, fondo: 2 })).toEqual([]);
  });
});
