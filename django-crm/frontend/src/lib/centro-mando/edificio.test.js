import { describe, it, expect } from 'vitest';
import { salasDe, pisosDe } from './departamentos.js';
import {
  edificioDe, ALTURA_DE_PISO, SEPARACION_SALAS, FONDO_DE_CIRCULACION, NUCLEO
} from './edificio.js';
import { aPantalla, aRejilla, ALTURA_UNIDAD, BALDOSA } from './escena/isometria.js';
import PORDEFECTO from './__fixtures__/organizacion-por-defecto.json';

/**
 * EL EDIFICIO, Y LA AFIRMACIÓN QUE HAY QUE MEDIR.
 *
 * La empresa entera era una rejilla plana: once salas sobre un mismo suelo. Se
 * veían todas y no se parecía a una empresa. Apilarlas en niveles introduce un
 * problema que la rejilla no tenía y que **no se ve mirando una captura hasta
 * que ya está mal**: en esta proyección un nivel más alto se dibuja más arriba
 * y tapa del nivel de abajo la zona de `gx + gy` pequeño.
 *
 * O sea que la pregunta no es «se ven tres pisos» —eso se ve— sino **si algún
 * escritorio quedó detrás de la losa del piso de arriba**. Un puesto tapado no
 * da error, no da aviso, y la escena sigue animándolo: un agente trabajando
 * donde nadie lo ve. Eso es lo que estas pruebas miden, invirtiendo la
 * proyección punto por punto.
 *
 * Es la misma clase de fallo que el mobiliario solapado —«parpadea»— y la misma
 * clase de prueba: afirmar sobre el EFECTO geométrico, no sobre que exista una
 * función que calcula posiciones.
 */

const SALAS = salasDe(PORDEFECTO);
const PISOS = pisosDe(PORDEFECTO, SALAS);
const inventario = [
  { nombre: 'supervisor_noc', area: 'Operaciones', cargo: 'Supervisor NOC' },
  { nombre: 'cliente_final', area: 'Atención al Cliente', cargo: 'Primera línea' },
  { nombre: 'soporte_tecnico_cliente', area: 'Soporte Técnico', cargo: 'Diagnóstico' },
  { nombre: 'ventas', area: 'Ventas', cargo: 'Comercial' },
  { nombre: 'facturacion_cliente', area: 'Facturación', cargo: 'Cobranza' },
  { nombre: 'configuracion_guiada', area: 'Administración', cargo: 'Gestión' }
];

const EDIFICIO = edificioDe(SALAS, inventario, PISOS);

/** El rectángulo de rejilla que ocupa el suelo de una planta, en absoluto. */
function huella(p) {
  return {
    gx0: p.origen.gx, gx1: p.origen.gx + p.mundo.ancho,
    gy0: p.origen.gy, gy1: p.origen.gy + p.mundo.fondo,
    gz: p.origen.gz
  };
}

/**
 * ¿La planta `arriba` tapa el punto de pantalla `pt`?
 *
 * Se invierte la proyección sobre el PLANO de esa planta: se le devuelve la
 * altura que la proyección le había restado y se pregunta en qué celda cae. Si
 * cae dentro de su suelo, su losa está delante de ese punto — porque se dibuja
 * después, por altura.
 *
 * Esto es exacto, no una aproximación por caja: el suelo de una planta es un
 * rombo en pantalla, y una caja envolvente daría falsos positivos en las cuatro
 * esquinas, que es justo donde los escritorios suelen estar.
 */
function tapa(arriba, pt) {
  const h = huella(arriba);
  const celda = aRejilla(pt.x, pt.y + h.gz * ALTURA_UNIDAD);
  return celda.x >= h.gx0 && celda.x <= h.gx1 && celda.y >= h.gy0 && celda.y <= h.gy1;
}

describe('la inversa de la proyección hace lo que esta prueba cree', () => {
  it('un punto del suelo de una planta cae dentro de su huella', () => {
    // Sin esto, `tapa()` podría devolver `false` siempre y todas las
    // comprobaciones de abajo pasarían sin comprobar nada. Es la mutación
    // hecha explícita.
    const p = { origen: { gx: 10, gy: 4, gz: 6 }, mundo: { ancho: 8, fondo: 6, alto: 4 } };
    expect(tapa(p, aPantalla(12, 6, 6))).toBe(true);
    expect(tapa(p, aPantalla(12, 6, 0))).toBe(false);
    expect(tapa(p, aPantalla(40, 40, 6))).toBe(false);
  });

  it('ida y vuelta de la proyección cierran', () => {
    const pt = aPantalla(7.5, 3.25, 0);
    const celda = aRejilla(pt.x, pt.y);
    expect(celda.x).toBeCloseTo(7.5, 6);
    expect(celda.y).toBeCloseTo(3.25, 6);
  });
});

describe('el edificio del piloto', () => {
  it('tiene un nivel por piso declarado', () => {
    expect(EDIFICIO.niveles.map((n) => n.nivel)).toEqual([3, 2, 1]);
  });

  it('y cada sala aparece exactamente una vez', () => {
    const ids = EDIFICIO.plantas.filter((p) => p.papel === 'sala').map((p) => p.sala);
    expect(ids.length).toBe(SALAS.length);
    expect(new Set(ids).size).toBe(SALAS.length);
  });

  it('cada nivel trae su circulación y su núcleo', () => {
    for (const n of EDIFICIO.niveles) {
      const suyas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel);
      expect(suyas.filter((p) => p.papel === 'circulacion').length, `piso ${n.nivel}`).toBe(1);
      expect(suyas.filter((p) => p.papel === 'nucleo').length, `piso ${n.nivel}`).toBe(1);
    }
  });

  it('los niveles se separan por la altura declarada', () => {
    const alturas = EDIFICIO.niveles.map((n) => n.gz);
    expect(alturas).toEqual([2 * ALTURA_DE_PISO, ALTURA_DE_PISO, 0]);
  });

  it('la separación cubre la profundidad de sala que hay DETRÁS del puesto', () => {
    // La condición medida, escrita como comprobación:
    //     (H − z) · 0,8125  >  fondo de la sala − gy del puesto
    // El caso que manda es la placa de un puesto normal, que va a 3,65 — más
    // alta que la silla, y por eso la que necesita más separación.
    const salas = EDIFICIO.plantas.filter((p) => p.papel === 'sala');
    let peor = 0;
    for (const s of salas) {
      for (const q of s.puestos) {
        peor = Math.max(peor, s.mundo.fondo - q.gy);
      }
    }
    expect((ALTURA_DE_PISO - 3.65) * 0.8125).toBeGreaterThan(peor);
  });

  it('y el aire que queda entre losas se llena de estructura', () => {
    // Bajar la separación taparía puestos, así que el hueco no se cierra: se
    // ocupa. Sin esto, quince unidades de aire son tres bandejas flotando —la
    // crítica exacta que trajo esta etapa.
    const alto = Math.max(...EDIFICIO.niveles.map((n) => n.nivel));
    for (const n of EDIFICIO.niveles) {
      const suyas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel);
      const nuc = suyas.find((p) => p.papel === 'nucleo');
      //  El núcleo sube la altura de piso entera: su remate llega a la losa
      //  del nivel de arriba y los núcleos apilados se leen como una caja.
      expect(nuc.mundo.alto, `nucleo del piso ${n.nivel}`).toBe(ALTURA_DE_PISO);
      const columnas = suyas.find((p) => p.papel === 'circulacion').mobiliario
        .filter((m) => m.tipo === 'columna');
      if (n.nivel === alto) {
        //  Una columna que no sostiene nada es un poste.
        expect(columnas.length, 'la cubierta no lleva columnas').toBe(0);
      } else {
        expect(columnas.length, `piso ${n.nivel}`).toBeGreaterThanOrEqual(3);
        expect(columnas.every((c) => c.alto === ALTURA_DE_PISO)).toBe(true);
      }
    }
  });

  it('y ninguna columna sube hasta el aire', () => {
    // Visto en el navegador, no deducido: el piso 1 tiene cinco salas y el 2
    // tiene tres, así que las columnas del tramo largo del 1 subían quince
    // unidades hasta donde no hay losa. Colgaban a la derecha del edificio y
    // se leían exactamente como lo que eran: postes.
    const porNivel = new Map(EDIFICIO.niveles.map((n) => [n.nivel, n]));
    for (const n of EDIFICIO.niveles) {
      const suyas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel);
      const paso = suyas.find((p) => p.papel === 'circulacion');
      const encima = [...porNivel.keys()].filter((x) => x > n.nivel).sort((a, b) => a - b)[0];
      const columnas = paso.mobiliario.filter((m) => m.tipo === 'columna');
      if (encima === undefined) {
        expect(columnas.length, 'la cubierta no lleva columnas').toBe(0);
        continue;
      }
      //  El borde de la losa de arriba, en coordenadas de esta planta.
      const arriba = EDIFICIO.plantas.filter((p) => p.nivel === encima);
      const borde = Math.max(...arriba.map((p) => p.origen.gx + p.mundo.ancho))
        - paso.origen.gx;
      for (const c of columnas) {
        expect(c.gx, `columna a ${c.gx} del piso ${n.nivel}`).toBeLessThanOrEqual(borde);
      }
    }
  });

  it('cada sala lleva su nombre en el canto de la losa', () => {
    // El cartel del muro de fondo queda detrás de la losa de arriba: con esta
    // separación el muro sólo se ve hasta 2,7 de sus 4 unidades y el cartel
    // vive a 3,63. Un nombre que a veces se ve no es un nombre.
    for (const p of EDIFICIO.plantas.filter((q) => q.papel === 'sala')) {
      expect(p.rotuloFrontal, p.sala).toBeTruthy();
      expect(p.rotuloFrontal).toBe(SALAS.find((s) => s.id === p.sala).rotulo);
    }
  });

  it('las salas van al FRENTE y la circulación al fondo', () => {
    // No es estética: es la única disposición en la que el piso de arriba tapa
    // el pasillo y no los escritorios.
    for (const p of EDIFICIO.plantas) {
      if (p.papel === 'sala') expect(p.origen.gy, p.sala).toBe(FONDO_DE_CIRCULACION);
      if (p.papel === 'circulacion') expect(p.origen.gy).toBe(0);
    }
  });

  it('el núcleo está en la misma huella en todos los niveles', () => {
    const nucleos = EDIFICIO.plantas.filter((p) => p.papel === 'nucleo');
    expect(new Set(nucleos.map((p) => `${p.origen.gx},${p.origen.gy}`)).size).toBe(1);
    expect(nucleos[0].mundo.ancho).toBe(NUCLEO.ancho);
  });

  it('y el núcleo es lo único cerrado: todo lo demás deja ver dentro', () => {
    // Una fachada que tape las oficinas es lo que un edificio isométrico no
    // puede tener.
    const circulaciones = EDIFICIO.plantas.filter((p) => p.papel === 'circulacion');
    expect(circulaciones.every((p) => p.muros === false)).toBe(true);
    expect(EDIFICIO.plantas.filter((p) => p.papel === 'nucleo')
      .every((p) => p.muros === true)).toBe(true);
  });

  it('cada losa de nivel lleva canto, y las salas baranda', () => {
    // Un suelo sin espesor se lee como una alfombra, y tres alfombras apiladas
    // no son un edificio.
    for (const p of EDIFICIO.plantas) {
      expect(p.losa, `${p.papel} del piso ${p.nivel}`).toBe(true);
    }
    for (const p of EDIFICIO.plantas.filter((q) => q.papel === 'sala')) {
      expect(p.baranda, p.sala).toBe(true);
    }
  });
});

describe('NINGÚN ESCRITORIO QUEDA DETRÁS DEL PISO DE ARRIBA', () => {
  //  La comprobación que justifica el archivo. Un puesto tapado no da error,
  //  no da aviso y la escena lo sigue animando: un agente trabajando donde
  //  nadie lo ve.
  const niveles = [...EDIFICIO.niveles].sort((a, b) => a.nivel - b.nivel);

  for (const n of niveles) {
    const arriba = EDIFICIO.plantas.filter((p) => p.origen.gz > n.gz);
    if (arriba.length === 0) continue;

    it(`piso ${n.nivel}: sus puestos se ven`, () => {
      const salas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel && p.papel === 'sala');
      expect(salas.length).toBeGreaterThan(0);
      for (const sala of salas) {
        for (const puesto of sala.puestos) {
          //  El punto del puesto en coordenadas del edificio, a la altura de
          //  la mesa: es donde está la silla y el personaje.
          const pt = aPantalla(
            sala.origen.gx + puesto.gx,
            sala.origen.gy + puesto.gy,
            sala.origen.gz + 0.9
          );
          for (const otra of arriba) {
            expect(tapa(otra, pt),
              `${sala.sala}/${puesto.local} tapado por ${otra.papel} del piso ${otra.nivel}`
            ).toBe(false);
          }
        }
      }
    });
  }

  it('y la placa de cada puesto tampoco', () => {
    // La placa va más alta que el puesto, así que puede quedar tapada aunque
    // la silla no. Es el mismo fallo un metro más arriba.
    for (const n of niveles) {
      const arriba = EDIFICIO.plantas.filter((p) => p.origen.gz > n.gz);
      for (const sala of EDIFICIO.plantas.filter((p) => p.nivel === n.nivel && p.papel === 'sala')) {
        for (const puesto of sala.puestos) {
          const pt = aPantalla(
            sala.origen.gx + puesto.gx,
            sala.origen.gy + puesto.gy,
            sala.origen.gz + (puesto.principal ? 2.9 : 3.65)
          );
          for (const otra of arriba) {
            expect(tapa(otra, pt),
              `placa de ${sala.sala}/${puesto.local} tapada por ${otra.papel} del piso ${otra.nivel}`
            ).toBe(false);
          }
        }
      }
    }
  });
});

describe('dentro de un nivel, nada se solapa', () => {
  it('ninguna planta del mismo nivel invade a otra', () => {
    for (const n of EDIFICIO.niveles) {
      const suyas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel);
      for (let i = 0; i < suyas.length; i++) {
        for (let j = i + 1; j < suyas.length; j++) {
          const a = huella(suyas[i]);
          const b = huella(suyas[j]);
          const choca = a.gx0 < b.gx1 && b.gx0 < a.gx1 && a.gy0 < b.gy1 && b.gy0 < a.gy1;
          expect(choca, `piso ${n.nivel}: ${suyas[i].papel} y ${suyas[j].papel}`).toBe(false);
        }
      }
    }
  });

  it('y el hueco entre salas vecinas cubre la ALTURA de un muro', () => {
    // En isometría un muro de cuatro unidades se proyecta más de cien píxeles
    // hacia arriba e invade la sala de atrás aunque en planta no se toquen.
    //  El muro de una SALA, no el del nucleo: el nucleo es una torre de la
    //  altura de piso entera y no es vecino de nadie en la fila. Medir contra
    //  el maximo de todas las plantas exigiria un hueco de quince celdas entre
    //  salas, que es tres veces lo que la geometria pide.
    const alto = Math.max(...EDIFICIO.plantas
      .filter((p) => p.papel === 'sala').map((p) => p.mundo.alto));
    for (const n of EDIFICIO.niveles) {
      const salas = EDIFICIO.plantas
        .filter((p) => p.nivel === n.nivel && p.papel === 'sala')
        .sort((a, b) => a.origen.gx - b.origen.gx);
      for (let i = 1; i < salas.length; i++) {
        const hueco = salas[i].origen.gx - (salas[i - 1].origen.gx + salas[i - 1].mundo.ancho);
        expect(hueco, `piso ${n.nivel}`).toBeGreaterThanOrEqual(alto);
      }
    }
    expect(SEPARACION_SALAS).toBeGreaterThanOrEqual(alto);
  });

  it('la circulación llega hasta la última sala del nivel más largo', () => {
    // Un pasillo que termina antes que las salas deja la última flotando sin
    // conexión, y eso es exactamente lo que el edificio vino a arreglar.
    for (const n of EDIFICIO.niveles) {
      const suyas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel);
      const paso = suyas.find((p) => p.papel === 'circulacion');
      const salas = suyas.filter((p) => p.papel === 'sala');
      const finSalas = Math.max(...salas.map((p) => p.origen.gx + p.mundo.ancho));
      expect(paso.origen.gx + paso.mundo.ancho, `piso ${n.nivel}`)
        .toBeGreaterThanOrEqual(finSalas);
    }
  });

  it('la circulación toca el núcleo', () => {
    for (const n of EDIFICIO.niveles) {
      const suyas = EDIFICIO.plantas.filter((p) => p.nivel === n.nivel);
      const paso = suyas.find((p) => p.papel === 'circulacion');
      const nuc = suyas.find((p) => p.papel === 'nucleo');
      expect(paso.origen.gx, `piso ${n.nivel}`).toBe(nuc.origen.gx + nuc.mundo.ancho);
    }
  });
});

describe('el edificio se adapta a la empresa, no al revés', () => {
  it('una empresa de una sola planta sale con un nivel', () => {
    const org = {
      pisos: [{ nivel: 1, rotulo: 'Planta' }],
      departamentos: ['a', 'b', 'c', 'd'].map((id) => ({
        id, rotulo: id.toUpperCase(), piso: 1, plantilla: 'tecnica', areas: [id]
      }))
    };
    const s = salasDe(org);
    const e = edificioDe(s, [], pisosDe(org, s));
    expect(e.niveles.length).toBe(1);
    expect(e.niveles[0].gz).toBe(0);
    expect(e.plantas.filter((p) => p.papel === 'sala').length).toBe(4);
  });

  it('una de cinco niveles sale con cinco, y el más bajo apoya en el suelo', () => {
    const org = {
      pisos: [1, 2, 3, 4, 5].map((nivel) => ({ nivel })),
      departamentos: Array.from({ length: 15 }, (_, i) => ({
        id: `d${i}`, rotulo: `D${i}`, piso: (i % 5) + 1, plantilla: 'expedientes',
        areas: [`a${i}`]
      }))
    };
    const s = salasDe(org);
    const e = edificioDe(s, [], pisosDe(org, s));
    expect(e.niveles.length).toBe(5);
    expect(Math.min(...e.niveles.map((n) => n.gz))).toBe(0);
    expect(e.plantas.filter((p) => p.papel === 'sala').length).toBe(15);
  });

  it('un sótano no rompe la referencia de altura', () => {
    // El nivel más bajo es la referencia, y se calcula del dato: asumir que el
    // más bajo es 1 dejaría un sótano a altura negativa, por debajo del suelo
    // que la cámara encuadra.
    const org = {
      pisos: [{ nivel: -1 }, { nivel: 1 }],
      departamentos: [
        { id: 'a', rotulo: 'A', piso: -1, plantilla: 'tecnica', areas: ['a'] },
        { id: 'b', rotulo: 'B', piso: 1, plantilla: 'tecnica', areas: ['b'] }
      ]
    };
    const s = salasDe(org);
    const e = edificioDe(s, [], pisosDe(org, s));
    expect(Math.min(...e.plantas.map((p) => p.origen.gz))).toBe(0);
    expect(e.niveles.find((n) => n.nivel === -1).gz).toBe(0);
  });

  it('sin organización no hay edificio, y no revienta', () => {
    expect(edificioDe([], [], []).plantas).toEqual([]);
    expect(edificioDe(null, [], null).plantas).toEqual([]);
    expect(edificioDe(SALAS, [], []).plantas).toEqual([]);
  });

  it('un nivel declarado y vacío no aporta salas pero sí su losa', () => {
    const org = {
      pisos: [{ nivel: 1 }, { nivel: 2 }],
      departamentos: [{ id: 'a', rotulo: 'A', piso: 1, plantilla: 'tecnica', areas: ['a'] }]
    };
    const s = salasDe(org);
    const e = edificioDe(s, [], pisosDe(org, s));
    expect(e.niveles.length).toBe(2);
    const dos = e.plantas.filter((p) => p.nivel === 2);
    expect(dos.filter((p) => p.papel === 'sala').length).toBe(0);
    expect(dos.filter((p) => p.papel === 'circulacion').length).toBe(1);
  });
});

describe('aislar un nivel', () => {
  const solo = edificioDe(SALAS, inventario, PISOS, { soloNivel: 2 });

  it('deja sólo ese nivel', () => {
    expect(solo.niveles.map((n) => n.nivel)).toEqual([2]);
    expect(solo.plantas.every((p) => p.nivel === 2)).toBe(true);
  });

  it('y lo BAJA al suelo', () => {
    // Un piso aislado flotando a dos pisos de altura no dice nada, y encuadrar
    // sobre el vacío deja la sala en una esquina.
    expect(solo.plantas.every((p) => p.origen.gz === 0)).toBe(true);
  });

  it('con sus salas, su circulación y su núcleo', () => {
    expect(solo.plantas.filter((p) => p.papel === 'sala').length).toBe(3);
    expect(solo.plantas.filter((p) => p.papel === 'circulacion').length).toBe(1);
    expect(solo.plantas.filter((p) => p.papel === 'nucleo').length).toBe(1);
  });

  it('y la estructura queda recortada: no hay nada arriba que sostener', () => {
    // Visto en el navegador: con el nivel de arriba fuera de la escena, las
    // columnas de quince unidades subían hasta el vacío y se veían como
    // mástiles que se comían la sala. Un muñón sigue diciendo que el edificio
    // continúa, que es lo único que tiene que decir cuando lo de arriba no se
    // está mirando.
    const paso = solo.plantas.find((p) => p.papel === 'circulacion');
    for (const c of paso.mobiliario.filter((m) => m.tipo === 'columna')) {
      expect(c.alto).toBeLessThan(ALTURA_DE_PISO);
    }
    expect(solo.plantas.find((p) => p.papel === 'nucleo').mundo.alto)
      .toBeLessThan(ALTURA_DE_PISO);
  });

  it('un nivel que no existe deja el edificio vacío, no el entero', () => {
    // Caer al edificio completo sería mostrar otra cosa que la pedida sin
    // decirlo.
    expect(edificioDe(SALAS, inventario, PISOS, { soloNivel: 99 }).plantas).toEqual([]);
  });
});

describe('el recinto que la cámara encuadra', () => {
  it('incluye la altura del nivel más alto', () => {
    // Tomar sólo el alto de las salas limitaba la cámara contra un recinto de
    // cuatro unidades y el tercer piso quedaba cortado por arriba.
    const masAlto = Math.max(...EDIFICIO.plantas.map((p) => p.origen.gz + p.mundo.alto));
    expect(EDIFICIO.mundo.alto).toBe(masAlto);
    expect(EDIFICIO.mundo.alto).toBeGreaterThan(2 * ALTURA_DE_PISO);
  });

  it('y llega hasta la última sala', () => {
    const fin = Math.max(...EDIFICIO.plantas.map((p) => p.origen.gx + p.mundo.ancho));
    expect(EDIFICIO.mundo.ancho).toBe(fin);
  });

  it('las medidas salen en celdas, no en píxeles', () => {
    // Si alguien mezclara las dos unidades acá, el encuadre saldría 32 veces
    // más grande y el síntoma sería «la escena aparece vacía».
    expect(EDIFICIO.mundo.ancho).toBeLessThan(BALDOSA.ancho * 10);
  });
});
