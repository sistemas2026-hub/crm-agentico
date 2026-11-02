import { describe, it, expect } from 'vitest';
import {
  ENTRADA, PATIO_MINIMO,
  columnasHasta, fondoObjetivo, repartirAnillo, repartirManzanas
} from './anillo.js';

/**
 * EL REPARTO DE LA SEDE.
 *
 * Esta guarda no existía, y el propio `anillo.js` afirmaba que sí: su
 * comentario decía «lo que sí da está medido en `anillo.test.js`» sobre un
 * archivo que nunca se escribió. Es exactamente lo que CLAUDE.md §6 llama
 * *una prueba que dice que algo existe no prueba que funcione*, en su forma
 * más barata: ni siquiera existía.
 *
 * Lo que mide es el EFECTO —cuánto suelo queda vacío, qué se mueve al crecer,
 * si dos salas se pisan— y no la presencia de un mecanismo.
 */

/** Una sala de mentira con el único campo que el reparto mira. */
const sala = (id, ancho, fondo) => ({ id, planta: { mundo: { ancho, fondo } } });

/** La empresa del piloto, con los tamaños reales que da `plantillasPara`. */
const PILOTO = [
  sala('operativo', 14, 10),
  sala('campo', 11, 8),
  sala('atencion_cliente', 13, 9),
  sala('comercial', 13, 10),
  sala('cartera', 12, 10),
  sala('administracion', 12, 9),
  sala('recursos_humanos', 12, 10),
  sala('auditoria', 12, 10),
  sala('direccion', 12, 9),
  sala('sala_reuniones', 12, 9),
  sala('recepcion', 13, 9)
];

const area = (r) => r.huella.ancho * r.huella.fondo;
const areaSalas = (r) => r.puestas.reduce((t, p) => t + p.ancho * p.fondo, 0);
const seSolapan = (a, b) =>
  a.x < b.x + b.ancho && b.x < a.x + a.ancho &&
  a.y < b.y + b.fondo && b.y < a.y + a.fondo;

/** Cuántas salas de cada tamaño, para probar formas raras. */
const empresaDe = (n) =>
  Array.from({ length: n }, (_, i) => sala(`d${i}`, 10 + (i % 5), 8 + (i % 4)));

describe('ninguna sala se pisa con otra', () => {
  it('ni en el piloto ni en empresas de 1 a 40 departamentos', () => {
    for (const lista of [PILOTO, ...Array.from({ length: 40 }, (_, i) => empresaDe(i + 1))]) {
      const { puestas } = repartirAnillo(lista);
      for (const a of puestas) {
        for (const b of puestas) {
          if (a === b) continue;
          expect(seSolapan(a, b), `${a.sala.id} pisa a ${b.sala.id}`).toBe(false);
        }
      }
    }
  });

  it('y ninguna invade el patio', () => {
    //  El patio es por donde se camina. Una sala metida dentro lo parte en dos
    //  y deja a las figuras de ambiente cruzando una pared.
    for (const lista of [PILOTO, empresaDe(7), empresaDe(23)]) {
      const { puestas, patio } = repartirAnillo(lista);
      for (const p of puestas) {
        expect(seSolapan(p, patio), `${p.sala.id} se mete en el patio`).toBe(false);
      }
    }
  });

  it('todas caen dentro de la huella', () => {
    const r = repartirAnillo(PILOTO);
    for (const p of r.puestas) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.x + p.ancho).toBeLessThanOrEqual(r.huella.ancho);
      expect(p.y + p.fondo).toBeLessThanOrEqual(r.huella.fondo);
    }
  });
});

describe('el suelo vacío, que es lo que se veía mal', () => {
  it('las salas ocupan más de la mitad del suelo del piloto', () => {
    //  LA CIFRA QUE ORIGINÓ ESTE ARCHIVO. El reparto anterior dejaba las salas
    //  en el **47%** y una columna entera vacía pegada al patio: 507 unidades
    //  que no eran patio ni eran nada, y que se leían junto con él como un
    //  único descampado en el medio de la empresa.
    const r = repartirAnillo(PILOTO);
    const ocupacion = areaSalas(r) / area(r);
    expect(ocupacion, `ocupación ${(ocupacion * 100).toFixed(0)}%`).toBeGreaterThan(0.6);
  });

  it('ninguna columna se queda con una sala sola mientras otra lleva cinco', () => {
    //  LA CAUSA, y no el síntoma. Cortar las columnas cada cinco salas hacía
    //  que la sexta se llevara una columna entera para ella: 13 de ancho por
    //  los 48 de fondo del edificio, con 9 ocupados.
    for (const lista of [PILOTO, ...Array.from({ length: 24 }, (_, i) => empresaDe(i + 2))]) {
      const objetivo = fondoObjetivo(lista);
      const { izquierda, derecha } = repartirManzanas(lista);
      for (const grupo of [izquierda, derecha]) {
        const cols = columnasHasta(grupo, objetivo);
        if (cols.length < 2) continue;
        const fondos = cols.map((c) => c.reduce((t, s) => t + s.planta.mundo.fondo, 0));
        const masHonda = Math.max(...fondos);
        const masCorta = Math.min(...fondos);
        //  Una columna puede quedar más corta que otra —las salas no se
        //  parten—, pero no vacía al lado de una llena.
        expect(masCorta * 2, `columnas de fondo ${fondos.join(', ')}`)
          .toBeGreaterThan(masHonda - Math.max(...lista.map((s) => s.planta.mundo.fondo)));
      }
    }
  });

  it('el suelo muerto se queda abajo del quinto, en cualquier tamaño de empresa', () => {
    //  AFIRMA EL EFECTO, no la paridad de fondos entre manzanas, que era el
    //  proxy que esta prueba usaba antes. Dos manzanas pueden quedar
    //  desparejas y desperdiciar poco, o parejas y desperdiciar mucho; lo que
    //  importa es el suelo que no es ni sala, ni patio, ni pasillo, ni
    //  entrada.
    //
    //  El peor caso medido sobre 1 a 40 salas es 19%, con tres. Con el tope de
    //  cuota del patio que se probó y se descartó, llegaba al 27%.
    let peor = { pct: 0, n: 0 };
    for (let n = 1; n <= 40; n++) {
      const r = repartirAnillo(empresaDe(n));
      const total = area(r);
      const muerto = total - areaSalas(r)
        - r.pasillos.reduce((t, p) => t + p.ancho * p.fondo, 0)
        - (r.patio ? r.patio.ancho * r.patio.fondo : 0)
        - r.entrada.ancho * r.entrada.fondo;
      if (muerto / total > peor.pct) peor = { pct: muerto / total, n };
    }
    expect(peor.pct, `${(peor.pct * 100).toFixed(0)}% con ${peor.n} salas`)
      .toBeLessThan(0.2);
  });
});

describe('cuánta oficina entra en pantalla', () => {
  //  En esta isometría la caja que ocupa el plano mide siempre 2:1, y lo único
  //  que cambia es qué fracción de ella es oficina: `2·área / (ancho+fondo)²`.
  const enPantalla = (r) => 2 * areaSalas(r) / ((r.huella.ancho + r.huella.fondo) ** 2);

  it('el plano elegido le gana al que estaba antes', () => {
    //  El reparto viejo daba 56 × 48 con 1276 de salas: 23,6% de la caja.
    const antes = 2 * 1276 / ((56 + 48) ** 2);
    expect(enPantalla(repartirAnillo(PILOTO))).toBeGreaterThan(antes);
  });

  it('y le gana a la cinta de una sala de fondo, sin tener que prohibirla', () => {
    //  Esa cinta deja casi cero suelo muerto y gana si uno mira solo el
    //  desperdicio. Por eso el criterio no es el desperdicio.
    const fondoMaximo = Math.max(...PILOTO.map((s) => s.planta.mundo.fondo));
    expect(fondoObjetivo(PILOTO)).toBeGreaterThan(fondoMaximo);
  });
});

describe('crecer no reubica lo que ya estaba', () => {
  it('sumar un departamento no cambia de manzana a ninguno de los anteriores', () => {
    //  La propiedad que el archivo afirmaba y nadie medía. No promete que la
    //  sala no se mueva —el plano entero puede cambiar de forma— sino que no
    //  cruce de lado, que es lo que haría irreconocible la oficina.
    for (let n = 1; n < 24; n++) {
      const antes = repartirManzanas(empresaDe(n));
      const despues = repartirManzanas(empresaDe(n + 1));
      const lado = (reparto) => new Map([
        ...reparto.izquierda.map((s) => [s.id, 'izquierda']),
        ...reparto.derecha.map((s) => [s.id, 'derecha'])
      ]);
      const a = lado(antes);
      const b = lado(despues);
      for (const [id, banda] of a) {
        expect(b.get(id), `con ${n + 1} salas, ${id} cambió de manzana`).toBe(banda);
      }
    }
  });

  it('el orden de salida es el de entrada, no el de las manzanas', () => {
    const r = repartirAnillo(PILOTO);
    expect(r.puestas.map((p) => p.sala.id)).toEqual(PILOTO.map((s) => s.id));
  });
});

describe('a toda sala se puede entrar', () => {
  /** ¿Comparten un tramo de borde estas dos cajas? */
  const pegadas = (a, b) => {
    const porLado = (Math.abs(a.x - (b.x + b.ancho)) < 0.01 || Math.abs(b.x - (a.x + a.ancho)) < 0.01)
      && !(a.y + a.fondo <= b.y || b.y + b.fondo <= a.y);
    const porFrente = (Math.abs(a.y - (b.y + b.fondo)) < 0.01 || Math.abs(b.y - (a.y + a.fondo)) < 0.01)
      && !(a.x + a.ancho <= b.x || b.x + b.ancho <= a.x);
    return porLado || porFrente;
  };

  it('ninguna sala queda sin frente a una circulación', () => {
    //  LA PREGUNTA QUE ORIGINÓ ESTE BLOQUE, hecha mirando una captura: «¿por
    //  dónde se entra a las oficinas que están atrás?». La respuesta medida
    //  era: por ningún lado. Con dos columnas por manzana y sin pasillo, la
    //  columna exterior daba contra el muro de la de adelante — **5 de 11
    //  salas** del piloto: NOC, Comercial, Recursos Humanos, Dirección y
    //  Recepción.
    for (const lista of [PILOTO, ...Array.from({ length: 24 }, (_, i) => empresaDe(i + 1))]) {
      const r = repartirAnillo(lista);
      const circulacion = [...r.pasillos, r.patio, r.entrada].filter(Boolean);
      for (const p of r.puestas) {
        expect(circulacion.some((c) => pegadas(p, c)),
          `${p.sala.id} no da a ninguna circulación (empresa de ${lista.length})`).toBe(true);
      }
    }
  });

  it('una sala más angosta que su columna igual llega al borde', () => {
    //  El corte que casi se escapa: una columna es tan ancha como su sala
    //  mayor, y la sala angosta dejaba el resto ENTRE ella y el pasillo. Dos
    //  unidades de suelo alcanzaban para dejarla sin entrada.
    const desparejas = [sala('ancha', 16, 9), sala('angosta', 9, 9), sala('media', 12, 10), sala('otra', 10, 8)];
    const r = repartirAnillo(desparejas);
    const circulacion = [...r.pasillos, r.patio, r.entrada].filter(Boolean);
    for (const p of r.puestas) {
      expect(circulacion.some((c) => pegadas(p, c)), `${p.sala.id} quedó corta`).toBe(true);
    }
  });

  it('los pasillos no pisan ninguna sala ni el patio', () => {
    for (const lista of [PILOTO, empresaDe(13), empresaDe(26)]) {
      const r = repartirAnillo(lista);
      for (const pasillo of r.pasillos) {
        for (const p of r.puestas) {
          expect(seSolapan(pasillo, p), `un pasillo pisa ${p.sala.id}`).toBe(false);
        }
        expect(seSolapan(pasillo, r.patio), 'un pasillo pisa el patio').toBe(false);
      }
    }
  });

  it('una manzana de una sola columna no gasta pasillo', () => {
    //  Da al patio y con eso alcanza. Un pasillo ahí es suelo pagado dos veces.
    const r = repartirAnillo([sala('a', 12, 9), sala('b', 12, 9)]);
    expect(r.pasillos).toEqual([]);
  });

  it('el patio nunca es más ancho que el departamento más grande', () => {
    //  LO QUE SEPARA UNA CALLE INTERIOR DE UN DESCAMPADO, y es una medida
    //  mejor que la cuota del suelo. Un patio más ancho que una oficina se lee
    //  como terreno sobrante por mucho que se lo amueble; uno más angosto se
    //  lee como el sitio por el que se pasa entre dos filas de oficinas.
    //
    //  Con `PATIO_MINIMO.ancho` en 14 el patio del piloto era más ancho que
    //  seis de sus once salas. Y en una empresa de veinte departamentos el
    //  patio proporcional llegaba a 18 contra oficinas de 14.
    for (let n = 1; n <= 30; n++) {
      const lista = empresaDe(n);
      const r = repartirAnillo(lista);
      const masAncha = Math.max(...lista.map((s) => s.planta.mundo.ancho));
      expect(r.patio.ancho, `con ${n} salas: patio ${r.patio.ancho} contra sala ${masAncha}`)
        .toBeLessThanOrEqual(Math.max(masAncha, PATIO_MINIMO.ancho));
    }
  });

  it('y el suelo que no es sala cae un 40%', () => {
    //  El reparto viejo dejaba 1275 de suelo que no era sala sobre un plano de
    //  2688 —el 47%—: el patio con su entrada (768) más la columna huérfana
    //  (507). Ahora son 759 sobre 2035, el 37%.
    const r = repartirAnillo(PILOTO);
    const noEsSala = area(r) - areaSalas(r);
    expect(noEsSala, `${noEsSala} de suelo que no es sala`).toBeLessThan(1275 * 0.65);
    expect(noEsSala / area(r)).toBeLessThan(0.4);
  });

  it('con una sola columna por manzana no hay oficinas atrás', () => {
    //  La respuesta a «¿por dónde se entra a las de atrás?» que no necesita
    //  pasillos: que no haya salas atrás. Hasta diecisiete salas el plano
    //  elegido es de una columna por manzana.
    const r = repartirAnillo(PILOTO);
    expect(r.pasillos).toEqual([]);
    const bordes = new Set(r.puestas.map((p) =>
      p.banda === 'izquierda' ? p.x + p.ancho : p.x));
    expect(bordes.size, 'todas comparten el borde del patio').toBe(2);
  });
});

describe('el patio y la entrada', () => {
  it('el patio queda entre las dos manzanas', () => {
    const r = repartirAnillo(PILOTO);
    const izq = r.puestas.filter((p) => p.banda === 'izquierda');
    const der = r.puestas.filter((p) => p.banda === 'derecha');
    expect(Math.max(...izq.map((p) => p.x + p.ancho))).toBeLessThanOrEqual(r.patio.x);
    expect(Math.min(...der.map((p) => p.x))).toBeGreaterThanOrEqual(r.patio.x + r.patio.ancho);
  });

  it('la entrada está al frente del patio y no fuera del edificio', () => {
    //  Colgarla del frente estiraba la huella con una franja de suelo pelado
    //  del 25% del plano. Medido, y por eso vive dentro.
    const r = repartirAnillo(PILOTO);
    expect(r.entrada.x).toBe(r.patio.x);
    expect(r.entrada.y).toBe(r.patio.y + r.patio.fondo);
    expect(r.entrada.y + r.entrada.fondo).toBe(r.huella.fondo);
    expect(r.entrada.fondo).toBe(ENTRADA.fondo);
  });

  it('el patio nunca baja del mínimo, por chica que sea la empresa', () => {
    for (const n of [1, 2, 3]) {
      const r = repartirAnillo(empresaDe(n));
      expect(r.patio.ancho).toBeGreaterThanOrEqual(PATIO_MINIMO.ancho);
    }
  });

  it('una empresa sin salas devuelve un plano vacío y no revienta', () => {
    for (const vacio of [[], null, undefined, [null, false]]) {
      const r = repartirAnillo(vacio);
      expect(r.puestas).toEqual([]);
      expect(r.huella.ancho).toBeGreaterThan(0);
      expect(r.huella.fondo).toBeGreaterThan(0);
    }
  });
});
