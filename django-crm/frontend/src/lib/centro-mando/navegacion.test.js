import { describe, it, expect } from 'vitest';
import { sedeDe } from './sede.js';
import { PLANTILLAS } from './plantillas.js';
import {
  CELDA, LIBRE, MURO,
  camino, celdaDe, conectividad, llegadaA, rejillaDe, transitable
} from './navegacion.js';

/**
 * LA REJILLA NAVEGABLE.
 *
 * Lo que mide este archivo no es que la rejilla exista: es que **desde el
 * pasillo se llega a todos los puestos**. Una oficina no está accesible porque
 * tenga un hueco dibujado en el muro; lo está cuando hay camino.
 *
 * Esa diferencia no es teórica. En cuanto hubo rejilla, encontró dos defectos
 * que ninguna prueba anterior podía ver y que no se notaban mirando:
 *
 *   - **Siete puestos** de Comercial y Auditoría no se alcanzaban: el macetero
 *     del borde del patio estaba justo delante de sus puertas. La puerta
 *     seguía dibujada.
 *   - Un octavo tenía su punto de llegada encima del mostrador de su sala.
 */

const BASES = Object.keys(PLANTILLAS).filter((n) => !/_\d+$/.test(n) && n !== 'generica');

const salasDe = (n) => Array.from({ length: n }, (_, i) => {
  const plantilla = BASES[i % BASES.length];
  return {
    id: `d${i}`, rotulo: `Departamento ${i}`, tipo: 'departamento', piso: 1,
    plantilla, planta: PLANTILLAS[plantilla]
  };
});

const circulacionesDe = (sede) => sede.plantas
  .filter((p) => p.papel === 'circulacion')
  .map((p) => ({
    x: p.origen.gx, y: p.origen.gy, ancho: p.mundo.ancho, fondo: p.mundo.fondo
  }));

describe('desde el pasillo se llega a todos los puestos', () => {
  it('en empresas de 1 a 14 departamentos, ninguno queda aislado', () => {
    //  LA AFIRMACIÓN QUE VALE, y la que la revisión pidió con esas palabras:
    //  «no declarar una oficina accesible si no existe una ruta válida desde
    //  el corredor principal».
    for (const n of [1, 2, 3, 5, 8, 11, 14]) {
      const sede = sedeDe(salasDe(n), []);
      const rejilla = rejillaDe(sede);
      const { alcanzables, aislados } = conectividad(rejilla, circulacionesDe(sede));
      expect(aislados, `con ${n} departamentos quedaron aislados: ${aislados.join(', ')}`)
        .toEqual([]);
      expect(alcanzables.length).toBe(rejilla.destinos.size);
    }
  });

  it('y hay un camino de verdad, no sólo alcance', () => {
    //  `conectividad` recorre en anchura; esto pide la ruta con A*. Las dos
    //  cosas pueden discrepar si el camino existe pero el punto de llegada
    //  elegido no es transitable.
    const sede = sedeDe(salasDe(11), []);
    const rejilla = rejillaDe(sede);
    const patio = sede.plantas.find(
      (p) => p.papel === 'circulacion' && p.mundo.fondo > 20);
    const origen = celdaDe(
      patio.origen.gx + patio.mundo.ancho / 2,
      patio.origen.gy + patio.mundo.fondo / 2);
    for (const id of rejilla.destinos.keys()) {
      const destino = llegadaA(rejilla, id);
      expect(destino, `${id} no tiene punto de llegada libre`).toBeTruthy();
      expect(camino(rejilla, origen, destino), `sin ruta hasta ${id}`).toBeTruthy();
    }
  });

  it('ningún mueble tapa una puerta por fuera', () => {
    //  EL DEFECTO QUE ENCONTRÓ LA REJILLA. «Un banco delante de una puerta es
    //  una puerta cerrada», y eso no se ve mirando: la puerta sigue dibujada.
    const sede = sedeDe(salasDe(11), []);
    const rejilla = rejillaDe(sede);
    for (const p of sede.plantas.filter((x) => x.papel === 'sala')) {
      const o = p.origen;
      const m = p.mundo;
      const afuera = [];
      if (m.puertaDerecha) {
        afuera.push([o.gx + m.ancho + 0.3, o.gy + (m.puertaDerecha[0] + m.puertaDerecha[1]) / 2]);
      }
      if (m.puertaLateral) {
        afuera.push([o.gx - 0.3, o.gy + (m.puertaLateral[0] + m.puertaLateral[1]) / 2]);
      }
      if (m.puertaFrente) {
        afuera.push([o.gx + (m.puertaFrente[0] + m.puertaFrente[1]) / 2, o.gy + m.fondo + 0.3]);
      }
      for (const [gx, gy] of afuera) {
        const c = celdaDe(gx, gy);
        expect(transitable(rejilla, c.cx, c.cy),
          `${p.sala}: hay algo delante de su puerta, en (${gx.toFixed(1)}, ${gy.toFixed(1)})`)
          .toBe(true);
      }
    }
  });
});

describe('la rejilla sale del plano y no de una lista escrita', () => {
  it('el patio y los pasillos son transitables', () => {
    const sede = sedeDe(salasDe(11), []);
    const rejilla = rejillaDe(sede);
    for (const c of circulacionesDe(sede)) {
      //  El centro de cada circulación, que es donde no hay mobiliario.
      const p = celdaDe(c.x + c.ancho / 2, c.y + c.fondo / 2);
      expect(transitable(rejilla, p.cx, p.cy),
        `la circulación en (${c.x}, ${c.y}) no se puede pisar`).toBe(true);
    }
  });

  it('los muros de las salas no se cruzan', () => {
    //  Se comprueba en el tramo del muro QUE NO ES PUERTA: el resto del muro
    //  de fondo de cada sala tiene que ser infranqueable.
    const sede = sedeDe(salasDe(11), []);
    const rejilla = rejillaDe(sede);
    for (const p of sede.plantas.filter((x) => x.papel === 'sala')) {
      const o = p.origen;
      const c = celdaDe(o.gx + p.mundo.ancho - 0.3, o.gy + 0.2);
      expect(rejilla.celdas[c.cy * rejilla.ancho + c.cx],
        `${p.sala}: su muro de fondo se puede cruzar`).not.toBe(LIBRE);
    }
  });

  it('cada puerta dibujada está abierta en la rejilla', () => {
    //  La geometría y el mapa se escriben UNA vez. Una puerta que se ve y por
    //  la que no se pasa es la clase de desacuerdo que aparece cuando hay dos.
    const sede = sedeDe(salasDe(11), []);
    const rejilla = rejillaDe(sede);
    const dibujadas = sede.plantas
      .filter((p) => p.papel === 'sala')
      .reduce((t, p) => t + [p.mundo.puerta, p.mundo.puertaLateral,
                             p.mundo.puertaDerecha, p.mundo.puertaFrente]
        .filter(Boolean).length, 0);
    expect(rejilla.puertas.length).toBe(dibujadas);
    expect(dibujadas).toBeGreaterThan(0);
  });

  it('lo que nadie declaró transitable, no lo es', () => {
    //  Fail-closed, igual que las listas blancas del motor: la rejilla nace
    //  entera de MURO y sólo se abre lo que el plano declara.
    const sede = sedeDe(salasDe(3), []);
    const rejilla = rejillaDe(sede);
    //  La esquina de afuera del plano nunca se abre.
    expect(rejilla.celdas[0]).toBe(MURO);
  });

  it('una sede vacía devuelve una rejilla vacía y no revienta', () => {
    const r = rejillaDe(sedeDe([], []));
    expect(r.ancho).toBe(0);
    expect(r.destinos.size).toBe(0);
    expect(conectividad(r, []).aislados).toEqual([]);
  });
});

describe('el camino', () => {
  it('no cruza la esquina entre dos muros', () => {
    //  El error clásico de una rejilla con ocho direcciones: se permite la
    //  diagonal y el personaje atraviesa el canto de una pared. Acá la
    //  diagonal exige que los DOS ortogonales estén libres.
    const rejilla = {
      ancho: 3, fondo: 3,
      celdas: new Uint8Array([
        LIBRE, MURO, MURO,
        MURO, LIBRE, MURO,
        MURO, MURO, LIBRE
      ]),
      puertas: [], destinos: new Map()
    };
    expect(camino(rejilla, { cx: 0, cy: 0 }, { cx: 2, cy: 2 })).toBe(null);
  });

  it('encuentra el camino cuando lo hay, y es continuo', () => {
    const rejilla = {
      ancho: 5, fondo: 3,
      celdas: new Uint8Array([
        LIBRE, LIBRE, LIBRE, LIBRE, LIBRE,
        MURO, MURO, LIBRE, MURO, MURO,
        LIBRE, LIBRE, LIBRE, LIBRE, LIBRE
      ]),
      puertas: [], destinos: new Map()
    };
    const ruta = camino(rejilla, { cx: 0, cy: 0 }, { cx: 0, cy: 2 });
    expect(ruta).toBeTruthy();
    //  Pasa por el único hueco.
    expect(ruta.some((c) => c.cx === 2 && c.cy === 1)).toBe(true);
    //  Y no se teletransporta: cada paso toca al anterior.
    for (let i = 1; i < ruta.length; i++) {
      expect(Math.max(Math.abs(ruta[i].cx - ruta[i - 1].cx),
                      Math.abs(ruta[i].cy - ruta[i - 1].cy))).toBe(1);
    }
  });

  it('devuelve null si el destino está tapiado, en vez de una ruta a medias', () => {
    const rejilla = {
      ancho: 3, fondo: 1,
      celdas: new Uint8Array([LIBRE, MURO, LIBRE]),
      puertas: [], destinos: new Map()
    };
    expect(camino(rejilla, { cx: 0, cy: 0 }, { cx: 2, cy: 0 })).toBe(null);
  });

  it('la celda es más fina que una persona', () => {
    //  Media unidad. Con celdas de una unidad, un vano de 1,8 daría una sola
    //  celda de paso y cualquier error de redondeo lo cerraría.
    expect(CELDA).toBeLessThanOrEqual(0.5);
  });
});

describe('la navegación no sabe nada del negocio', () => {
  //  «El algoritmo de navegación no debe saber nada de facturación, NOC,
  //  ventas o herramientas de IA. Su responsabilidad debe ser exclusivamente
  //  mover personajes por una geometría válida». Es lo que permite reutilizarlo
  //  el día que haya visitantes, personal humano u otros elementos móviles.
  //
  //  La guarda de `escena/` ya vigila esa carpeta; estos dos archivos viven
  //  fuera y nadie los miraba.
  const PROHIBIDAS = [
    'wisphub', 'smartolt', 'bottlecrm', 'ticket', 'herramienta', 'isp',
    'rapilink', 'factura', 'suscriptor', 'agente', 'noc', 'cartera'
  ];

  it('ni `navegacion.js` ni `paseo.js` nombran el negocio', async () => {
    const fs = await import('node:fs');
    const archivos = ['navegacion.js', 'paseo.js'];
    for (const archivo of archivos) {
      const texto = fs.readFileSync(`src/lib/centro-mando/${archivo}`, 'utf8');
      for (const palabra of PROHIBIDAS) {
        const re = new RegExp(String.raw`\b${palabra}\b`, 'i');
        expect(re.test(texto), `«${palabra}» aparece en ${archivo}`).toBe(false);
      }
    }
  });

  it('y la guarda se pondría roja si lo hicieran', () => {
    //  LA MUTACIÓN EXPLÍCITA, y acá se ganó el sueldo.
    //
    //  La primera versión de este archivo se escribió con un heredoc que se
    //  comió una barra, y la expresión quedó con un RETROCESO -el carácter
    //  U+0008- en vez de un límite de palabra. La guarda de arriba pasaba en
    //  verde SIN COMPARAR NADA: no encontraba ninguna palabra prohibida
    //  porque no buscaba ninguna.
    //
    //  Por eso las dos usan `String.raw`: dentro de una plantilla o de una
    //  cadena normal, `\b` es un escape, no un límite de palabra.
    const re = new RegExp(String.raw`\bagente\b`, 'i');
    expect(re.test('const nombreDelAgente = 1')).toBe(false);
    expect(re.test('// el agente que ejecuta')).toBe(true);
  });

  it('lo que `rejillaDe` recibe es geometría y nada más', () => {
    //  Una sede de mentira, sin un solo dato de empresa, tiene que producir
    //  una rejilla válida.
    const sede = {
      mundo: { ancho: 10, fondo: 10 },
      plantas: [
        { papel: 'circulacion', origen: { gx: 4, gy: 0 }, mundo: { ancho: 2, fondo: 10 } },
        {
          papel: 'sala', sala: 'x', origen: { gx: 0, gy: 0 },
          mundo: { ancho: 4, fondo: 6, puertaDerecha: [1, 2.8], antepecho: { derecha: true } },
          puestos: [{ id: 'x:1', gx: 1.5, gy: 3 }], mobiliario: []
        }
      ]
    };
    const r = rejillaDe(sede);
    expect(r.destinos.size).toBe(1);
    expect(conectividad(r, [{ x: 4, y: 0, ancho: 2, fondo: 10 }]).aislados).toEqual([]);
  });
});
