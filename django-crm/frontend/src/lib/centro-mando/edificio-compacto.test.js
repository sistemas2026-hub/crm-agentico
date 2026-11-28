import { describe, it, expect } from 'vitest';
import { salasDe, pisosDe } from './departamentos.js';
import { edificioDe, ALTURA_DE_PISO } from './edificio.js';
import { edificioCompactoPixi } from './edificio-compacto.js';
import { aPantalla, aRejilla, ALTURA_UNIDAD } from './escena/isometria.js';
import PORDEFECTO from './__fixtures__/organizacion-por-defecto.json';

/**
 * LA OPCIÓN B, Y LA AFIRMACIÓN MÍA QUE TIRÓ.
 *
 * El 01/11/2026 dije que la planta compacta exigía en PixiJS 28,7 unidades de
 * aire entre losas —una torre de 86 para 40 de planta— y que por eso hacía
 * falta otro motor. Era una estimación presentada como una medición. Estas
 * pruebas la miden con la inversa de la proyección, la misma de
 * `edificio.test.js`, y dicen lo contrario: **a la altura de piso actual la
 * planta compacta no tapa ni un puesto.**
 *
 * Lo que sí queda en pie, y es el aporte de la comparación, está en el último
 * bloque: que no se tape a 15 no es una garantía, es una coincidencia de la
 * rejilla. Entre 16 y 29 se vuelve a tapar. La prueba que afirma eso es la que
 * importa, porque es la que impide que alguien «arregle» la altura de piso y
 * esconda puestos sin un solo error en la consola.
 */

const inventario = [
  { nombre: 'supervisor_noc', area: 'Operaciones', cargo: 'Supervisor NOC' },
  { nombre: 'cliente_final', area: 'Atención al Cliente', cargo: 'Primera línea' },
  { nombre: 'soporte_tecnico_cliente', area: 'Soporte Técnico', cargo: 'Diagnóstico' },
  { nombre: 'ventas', area: 'Ventas', cargo: 'Comercial' },
  { nombre: 'facturacion_cliente', area: 'Facturación', cargo: 'Cobranza' },
  { nombre: 'configuracion_guiada', area: 'Administración', cargo: 'Gestión' }
];

/**
 * La empresa del piloto: ocho departamentos y tres espacios en tres pisos. Es
 * la misma con la que se midió el spike de Three.js, para que las dos columnas
 * de la comparación hablen de la misma empresa.
 */
function empresaDelPiloto() {
  const dep = (id, piso, plantilla) => ({ id, rotulo: id, piso, plantilla, ocupaciones: [] });
  return {
    pisos: [
      { nivel: 3, rotulo: 'Tecnología y dirección' },
      { nivel: 2, rotulo: 'Operación y clientes' },
      { nivel: 1, rotulo: 'Administración' }
    ],
    departamentos: [
      dep('noc', 3, 'tecnica'),
      dep('campo', 2, 'operaciones'),
      dep('atencion', 2, 'atencion'),
      dep('comercial', 2, 'comercial'),
      dep('finanzas', 1, 'expedientes'),
      dep('administracion', 1, 'generica'),
      dep('rrhh', 1, 'generica'),
      dep('auditoria', 1, 'expedientes')
    ],
    espacios: [
      { id: 'direccion', rotulo: 'Dirección', piso: 3, plantilla: 'generica', ocupaciones: [] },
      { id: 'reuniones', rotulo: 'Sala de Reuniones', piso: 2, plantilla: 'reuniones', ocupaciones: [] },
      { id: 'recepcion', rotulo: 'Recepción', piso: 1, plantilla: 'generica', ocupaciones: [] }
    ]
  };
}

function armar(org) {
  const salas = salasDe(org);
  return { salas, pisos: pisosDe(org, salas) };
}

const PILOTO = armar(empresaDelPiloto());
const DEFECTO = armar(PORDEFECTO);

/* --------------------------------------------------------------- oclusión */

/** El rectángulo de rejilla que ocupa el suelo de una planta, en absoluto. */
const huellaDe = (p) => ({
  gx0: p.origen.gx, gx1: p.origen.gx + p.mundo.ancho,
  gy0: p.origen.gy, gy1: p.origen.gy + p.mundo.fondo,
  gz: p.origen.gz
});

/**
 * ¿La planta `arriba` tapa el punto de pantalla `pt`?
 *
 * Le devuelve al punto la altura que la proyección le restó y pregunta en qué
 * celda del suelo de `arriba` cae. Exacto, no una caja envolvente: el suelo es
 * un rombo en pantalla y una caja daría falsos positivos en las esquinas, que
 * es justo donde están los escritorios.
 */
function tapa(arriba, pt) {
  const h = huellaDe(arriba);
  const celda = aRejilla(pt.x, pt.y + h.gz * ALTURA_UNIDAD);
  return celda.x >= h.gx0 && celda.x <= h.gx1 && celda.y >= h.gy0 && celda.y <= h.gy1;
}

/** La parte más alta de un puesto normal: lo que no la tapa, no tapa nada. */
const PLACA = 3.65;

/** Qué puestos quedan detrás de algo de un piso superior. */
function puestosTapados(edificio) {
  return quienTapa(edificio).map((t) => t.puesto);
}

/** Lo mismo, pero diciendo QUÉ pieza tapa: sin eso no se sabe qué arreglar. */
function quienTapa(edificio) {
  const tapados = [];
  const salas = edificio.plantas.filter((p) => p.papel === 'sala');
  for (const sala of salas) {
    const arriba = edificio.plantas.filter((p) => (p.origen.gz ?? 0) > (sala.origen.gz ?? 0));
    for (const q of sala.puestos) {
      const pt = aPantalla(sala.origen.gx + q.gx, sala.origen.gy + q.gy,
                           (sala.origen.gz ?? 0) + PLACA);
      for (const otra of arriba) {
        if (tapa(otra, pt)) {
          tapados.push({
            puesto: `${sala.sala}/${q.local}`,
            pieza: otra.arquitectura?.tipo ?? otra.papel
          });
          break;
        }
      }
    }
  }
  return tapados;
}

describe('la inversa de la proyección hace lo que esta prueba cree', () => {
  it('un punto del suelo de una planta cae dentro de su huella', () => {
    //  Sin esto, `tapa()` podría devolver `false` siempre y TODO lo de abajo
    //  pasaría sin comprobar nada. Es la mutación hecha explícita, y es la
    //  misma guarda que lleva `edificio.test.js`.
    const p = { origen: { gx: 10, gy: 4, gz: 6 }, mundo: { ancho: 8, fondo: 6, alto: 4 } };
    expect(tapa(p, aPantalla(12, 6, 6))).toBe(true);
    expect(tapa(p, aPantalla(12, 6, 0))).toBe(false);
    expect(tapa(p, aPantalla(40, 40, 6))).toBe(false);
  });

  it('y mide puestos de verdad: hay puestos que medir', () => {
    //  Si `puestosTapados` recorriera una lista vacía devolvería `[]` y las
    //  afirmaciones de visibilidad pasarían sin mirar nada.
    const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos);
    const cuantos = ed.plantas
      .filter((p) => p.papel === 'sala')
      .reduce((n, s) => n + s.puestos.length, 0);
    expect(cuantos).toBeGreaterThan(20);
  });
});

/* ------------------------------------------------------------ composición */

describe('B compone la planta compacta con el motor de A', () => {
  it('el edificio deja de ser una franja: la esbeltez baja de 4 a menos de 2', () => {
    for (const caso of [PILOTO, DEFECTO]) {
      const a = edificioDe(caso.salas, inventario, caso.pisos).mundo;
      const b = edificioCompactoPixi(caso.salas, inventario, caso.pisos).mundo;
      expect(a.ancho / a.fondo).toBeGreaterThan(4);
      expect(b.ancho / b.fondo).toBeLessThan(2);
    }
  });

  it('las salas van en varias filas, no en una sola', () => {
    const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos);
    const porNivel = new Map();
    for (const s of ed.plantas.filter((p) => p.papel === 'sala')) {
      porNivel.set(s.nivel, Math.max(porNivel.get(s.nivel) ?? 0, s.celda.fila));
    }
    //  El piso con más salas tiene más de una fila. Un piso de una sola sala
    //  sigue teniendo una fila, y eso no es un defecto.
    expect(Math.max(...porNivel.values())).toBeGreaterThan(0);
  });

  it('ninguna sala se superpone con otra del mismo piso', () => {
    for (const caso of [PILOTO, DEFECTO]) {
      const salas = edificioCompactoPixi(caso.salas, inventario, caso.pisos)
        .plantas.filter((p) => p.papel === 'sala');
      for (const a of salas) {
        for (const b of salas) {
          if (a === b || a.nivel !== b.nivel) continue;
          const cruza =
            a.origen.gx < b.origen.gx + b.mundo.ancho &&
            b.origen.gx < a.origen.gx + a.mundo.ancho &&
            a.origen.gy < b.origen.gy + b.mundo.fondo &&
            b.origen.gy < a.origen.gy + a.mundo.fondo;
          expect(cruza, `${a.sala} se mete en ${b.sala}`).toBe(false);
        }
      }
    }
  });

  it('todas las salas declaradas están, y ninguna inventada', () => {
    const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos);
    const puestas = ed.plantas.filter((p) => p.papel === 'sala').map((p) => p.sala).sort();
    expect(puestas).toEqual(PILOTO.salas.map((s) => s.id).sort());
  });

  it('una empresa sin estructura no produce edificio', () => {
    //  No inventar un edificio es la restricción, y acá es donde se mide.
    expect(edificioCompactoPixi([], inventario, PILOTO.pisos).plantas).toEqual([]);
    expect(edificioCompactoPixi(PILOTO.salas, inventario, []).plantas).toEqual([]);
  });

  it('cada planta cumple el contrato entero, también las de arquitectura', () => {
    //  Un `puestos: undefined` en una pieza de edificio no falla donde ocurre:
    //  la pantalla hace `plantas.flatMap(p => p.puestos)` y revienta tres
    //  `$derived` más tarde. Costó un 500 el 31/10/2026.
    const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos);
    for (const p of ed.plantas) {
      expect(Array.isArray(p.puestos), `${p.papel} sin puestos`).toBe(true);
      expect(Array.isArray(p.mobiliario), `${p.papel} sin mobiliario`).toBe(true);
      expect(p.mundo.ancho, `${p.papel} sin ancho`).toBeGreaterThan(0);
    }
  });
});

/* ------------------------------------------------- aislamiento de un piso */

describe('un piso aislado baja al suelo y se dibuja solo', () => {
  it('sólo salen sus salas', () => {
    const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos, { soloNivel: 2 });
    const niveles = new Set(
      ed.plantas.filter((p) => p.papel === 'sala').map((p) => p.nivel));
    expect([...niveles]).toEqual([2]);
  });

  it('y a cota cero, no flotando a dos pisos de altura', () => {
    for (const n of [1, 2, 3]) {
      const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos, { soloNivel: n });
      for (const s of ed.plantas.filter((p) => p.papel === 'sala')) {
        expect(s.origen.gz, `piso ${n} flotando`).toBe(0);
      }
    }
  });

  it('aislado no hay nada encima, así que no hay nada que tapar', () => {
    for (const n of [1, 2, 3]) {
      expect(puestosTapados(
        edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos, { soloNivel: n })
      )).toEqual([]);
    }
  });

  it('y aislado no lleva cubierta: una cubierta sobre el vacío tapa la planta', () => {
    //  Esto NO pasaba. La primera versión remataba igual que el edificio
    //  entero y la cubierta, sobre una huella de 39 de fondo, escondía diez
    //  puestos del único piso que se estaba mirando. Es la misma lección que
    //  las columnas cortadas a 2,5 en `edificio.js`.
    const ed = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos, { soloNivel: 1 });
    expect(ed.plantas.some((p) => p.arquitectura?.tipo === 'cubierta')).toBe(false);
  });
});

/* ------------------------------------------- la visibilidad, y su fragilidad */

describe('la planta compacta SÍ se ve en PixiJS, y mi estimación estaba mal', () => {
  it('a la altura de piso actual, los pisos no se tapan entre sí', () => {
    //  Esta es la afirmación que corrige la mía del 01/11/2026. No hace falta
    //  una torre: con la losa por sala que este motor ya usa, los pasillos del
    //  piso de arriba caen donde están los escritorios del de abajo, y las
    //  salas, el núcleo y el basamento no tapan ni un puesto.
    for (const caso of [PILOTO, DEFECTO]) {
      expect(puestosTapados(
        edificioCompactoPixi(caso.salas, inventario, caso.pisos, { cubierta: false })
      )).toEqual([]);
    }
  });

  it('el edificio queda compacto y el doble de alto que en tres dimensiones', () => {
    //  21 unidades en Three.js contra 42 acá, con la misma planta: el precio
    //  de resolver la oclusión separando pisos en vez de con profundidad.
    const b = edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos).mundo;
    expect(b.alto).toBe(ALTURA_DE_PISO * PILOTO.pisos.length);
    expect(b.alto).toBeGreaterThan(40);
  });
});

describe('lo que no cabe en 2.5D no son las oficinas: es la cubierta', () => {
  it('con cubierta se tapan puestos, y la cubierta es la ÚNICA culpable', () => {
    //  EL HALLAZGO DE LA COMPARACIÓN, y no se parece a lo que yo esperaba.
    //
    //  La planta compacta entra: ninguna sala tapa a otra, ni el núcleo, ni el
    //  basamento. Lo que no entra es el remate. Una cubierta sobre una huella
    //  de 39 celdas de fondo tiene que ser cruzada por la proyección entera, y
    //  esconde nueve puestos de los pisos de arriba. En la distribución lineal
    //  ese mismo remate no tapa nada, porque su huella tiene 18 de fondo.
    //
    //  Y un edificio sin cubierta no se lee como un edificio, así que esto no
    //  es un detalle de acabado: es el límite de la opción B.
    const culpas = quienTapa(edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos));
    expect(culpas.length).toBeGreaterThan(0);
    expect([...new Set(culpas.map((c) => c.pieza))]).toEqual(['cubierta']);
  });

  it('y quitarla deja el edificio limpio, sin tocar nada más', () => {
    expect(puestosTapados(
      edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos, { cubierta: false })
    )).toEqual([]);
  });

  it('con cubierta, la altura de piso que haría falta triplica el edificio', () => {
    //  Medido entero, de 15 a 130: la primera altura sin puestos tapados es 38.
    //  O sea un edificio de 114 unidades sobre una planta de 39 × 39, contra
    //  21 sobre 40 × 38 en tres dimensiones reales CON cubierta y CON recorte.
    const con = (h) => puestosTapados(
      edificioCompactoPixi(PILOTO.salas, inventario, PILOTO.pisos, { alturaDePiso: h }));
    expect(con(37).length).toBeGreaterThan(0);
    expect(con(38)).toEqual([]);
  });
});

describe('y la visibilidad de las oficinas es una coincidencia de la rejilla', () => {
  it('hay alturas de piso a las que se tapan puestos, y no son absurdas', () => {
    //  LA PRUEBA QUE IMPORTA DE TODO EL ARCHIVO.
    //
    //  Si la visibilidad fuera una propiedad del diseño, subir la altura de
    //  piso sólo podría mejorarla. No lo es: a 15 se ve entera, y entre 16 y
    //  29 —alturas que cualquiera elegiría para dar más aire— se tapan de dos
    //  a cuatro puestos. Un puesto tapado no da error y la escena lo sigue
    //  animando.
    //
    //  Esta prueba existe para que quien suba `ALTURA_DE_PISO` se entere.
    const rotos = [];
    for (let h = 16; h <= 29; h++) {
      //  SIN CUBIERTA, para que esto mida la rejilla y no el remate: con
      //  cubierta se tapan puestos a cualquier altura menor que 38 y la
      //  prueba pasaria sin decir nada de las filas.
      const tapados = puestosTapados(edificioCompactoPixi(
        PILOTO.salas, inventario, PILOTO.pisos, { alturaDePiso: h, cubierta: false }));
      if (tapados.length > 0) rotos.push(h);
    }
    expect(rotos.length,
      'si esto da 0, la visibilidad pasó a ser monótona y la comparación cambia'
    ).toBeGreaterThan(0);
  });

  it('y bajar la altura las tapa en serio', () => {
    const tapados = puestosTapados(edificioCompactoPixi(
      PILOTO.salas, inventario, PILOTO.pisos, { alturaDePiso: 7, cubierta: false }));
    //  Siete es la altura con la que el spike de Three.js dibuja el edificio
    //  de 21 unidades. En 2.5D, esa misma altura esconde media empresa.
    expect(tapados.length).toBeGreaterThan(10);
  });

  it('una losa corrida por piso —la que parece un piso— no cabe a esta altura', () => {
    //  Lo que hace que un nivel se lea como un nivel y no como bandejas
    //  sueltas es el suelo continuo. Con él la altura mínima sube a 38: una
    //  torre de 114 unidades para 40 de planta. ESE era el número que yo
    //  atribuí al caso general, y sólo vale para esta variante.
    const conCorrida = puestosTapados(edificioCompactoPixi(
      PILOTO.salas, inventario, PILOTO.pisos, { losaCorrida: true, cubierta: false }));
    expect(conCorrida.length).toBeGreaterThan(10);

    const alta = puestosTapados(edificioCompactoPixi(
      PILOTO.salas, inventario, PILOTO.pisos,
      { losaCorrida: true, cubierta: false, alturaDePiso: 38 }));
    expect(alta).toEqual([]);
  });
});
