/**
 * EL CATÁLOGO DE SALAS Y SUS TAMAÑOS.
 *
 * Las salas grandes se GENERAN, así que lo que hay que vigilar no es que
 * existan: es que lo generado sea una sala y no un dibujo roto. Una silla
 * dentro de una pared, dos sillas en el mismo punto o una sala que crece hacia
 * el fondo no dan error — dan una oficina en la que alguien trabaja donde nadie
 * lo ve.
 */
import { describe, it, expect } from 'vitest';
import { PLANTILLAS, PLANTILLA_DE_RESERVA, plantillaDe } from './plantillas.js';
import DEL_MOTOR from './__fixtures__/plantillas-del-motor.json';

const TODAS = Object.entries(PLANTILLAS);

describe('toda sala del catálogo es dibujable', () => {
  it('ningún puesto cae fuera de su sala', () => {
    // La mutación que mata: ampliar la fila sin ensanchar el mundo. El
    // escritorio quedaría atravesando el muro y la escena lo dibujaría igual.
    for (const [nombre, p] of TODAS) {
      for (const s of p.puestos) {
        expect(s.gx, `${nombre}/${s.id} gx`).toBeGreaterThanOrEqual(0);
        expect(s.gx, `${nombre}/${s.id} gx`).toBeLessThanOrEqual(p.mundo.ancho);
        expect(s.gy, `${nombre}/${s.id} gy`).toBeGreaterThanOrEqual(0);
        expect(s.gy, `${nombre}/${s.id} gy`).toBeLessThanOrEqual(p.mundo.fondo);
      }
    }
  });

  it('ningún puesto se repite de identificador', () => {
    // Dos `p3` serían dos ocupaciones del mismo puesto, que el esquema del
    // motor rechaza: la sala no se podría guardar y nadie sabría por qué.
    for (const [nombre, p] of TODAS) {
      const ids = p.puestos.map((s) => s.id);
      expect(new Set(ids).size, `${nombre}`).toBe(ids.length);
    }
  });

  it('ningún puesto se superpone con otro', () => {
    // Dos escritorios en el mismo punto dibujan uno solo, y la oficina se ve
    // con menos gente de la que tiene.
    for (const [nombre, p] of TODAS) {
      const puntos = p.puestos.map((s) => `${s.gx}|${s.gy}`);
      expect(new Set(puntos).size, `${nombre}`).toBe(puntos.length);
    }
  });

  it('toda sala tiene un puesto principal, y uno solo', () => {
    for (const [nombre, p] of TODAS) {
      expect(p.puestos.filter((s) => s.principal).length, nombre).toBe(1);
    }
  });
});

describe('los tamaños', () => {
  const variantes = TODAS.filter(([n]) => /_\d+$/.test(n));

  it('hay variantes, y su nombre dice cuántos puestos tienen', () => {
    // Si el nombre y el contenido se separan, la empresa elige «10 puestos» y
    // recibe otra cosa sin un error.
    expect(variantes.length).toBeGreaterThan(0);
    for (const [nombre, p] of variantes) {
      expect(p.puestos.length, nombre).toBe(Number(nombre.split('_').pop()));
    }
  });

  it('CRECEN A LO ANCHO Y NUNCA HACIA EL FONDO', () => {
    // No es estética. La separación entre pisos salió de invertir la
    // proyección: un puesto queda tapado por el nivel de arriba cuando
    // `(ALTURA_DE_PISO - z) * 0.8125 <= fondo - gy`. Crecer en fondo esconde
    // los escritorios nuevos bajo el piso de arriba, y la escena los sigue
    // animando donde nadie los ve. `gx` no aparece en esa condición.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      expect(p.mundo.fondo, `${nombre} fondo`).toBe(base.mundo.fondo);
      expect(p.mundo.alto, `${nombre} alto`).toBe(base.mundo.alto);
      expect(p.mundo.ancho, `${nombre} ancho`).toBeGreaterThan(base.mundo.ancho);
    }
  });

  it('ningún puesto nuevo va más atrás que los que ya estaban', () => {
    // El otro lado de la misma desigualdad: menos `gy` tapa igual que más
    // fondo.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      const minimoBase = Math.min(...base.puestos.map((s) => s.gy));
      expect(Math.min(...p.puestos.map((s) => s.gy)), nombre).toBeGreaterThanOrEqual(minimoBase);
    }
  });

  it('CAMBIAR DE TAMAÑO NO DESENTA A NADIE', () => {
    // Los puestos de la sala chica siguen llamándose igual en la grande. Si
    // `principal` o `p1` cambiaran de nombre, agrandar un departamento dejaría
    // a sus agentes en puestos que ya no existen: el motor los reportaría como
    // «puesto desconocido» y la oficina se vaciaría sola.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      const ids = new Set(p.puestos.map((s) => s.id));
      for (const s of base.puestos) expect(ids.has(s.id), `${nombre} perdió ${s.id}`).toBe(true);
    }
  });

  it('la sala de reserva NO tiene tamaños', () => {
    // Es a la que se cae cuando la plantilla pedida no existe. Ofrecer tamaños
    // de una sala de reserva sería ofrecer elegir el error.
    expect(TODAS.filter(([n]) => n.startsWith(`${PLANTILLA_DE_RESERVA}_`))).toEqual([]);
  });

  it('el cartel queda dentro de la sala y no pegado al muro viejo', () => {
    for (const [nombre, p] of variantes) {
      expect(p.cartel.gx, nombre).toBeGreaterThan(p.mundo.ancho * 0.2);
      expect(p.cartel.gx, nombre).toBeLessThan(p.mundo.ancho * 0.8);
    }
  });
});

describe('el catálogo del motor y el del frontend no se separan', () => {
  it('toda plantilla que ofrece el motor existe acá, con sus mismos puestos', () => {
    // Son dos listas en dos lenguajes: el motor sirve NOMBRES y la geometría
    // vive acá. Separadas, el formulario ofrece una sala que la oficina dibuja
    // como «Sala sin plantilla» — degrada visible, pero es un defecto igual.
    // El fixture lo genera `cli/exportar_organizacion.py`.
    for (const pl of DEL_MOTOR) {
      expect(Object.keys(PLANTILLAS), `el motor ofrece ${pl.nombre}`).toContain(pl.nombre);
      expect(PLANTILLAS[pl.nombre].puestos.length, pl.nombre).toBe(pl.puestos);
    }
  });

  it('y toda plantilla de acá la ofrece el motor', () => {
    // La otra dirección: una sala que existe y nadie puede elegir es código
    // que no corre.
    const ofrecidas = new Set(DEL_MOTOR.map((p) => p.nombre));
    for (const nombre of Object.keys(PLANTILLAS)) {
      if (nombre === PLANTILLA_DE_RESERVA) continue; // no se elige: se cae en ella
      expect(ofrecidas, `${nombre} no se puede elegir`).toContain(nombre);
    }
  });
});

describe('plantillaDe', () => {
  it('una plantilla desconocida cae en la de reserva Y lo dice', () => {
    const r = plantillaDe('inventada');
    expect(r.plantilla).toBe(PLANTILLAS[PLANTILLA_DE_RESERVA]);
    expect(r.faltante).toBe('inventada');
  });

  it('una conocida no reporta faltante', () => {
    expect(plantillaDe('tecnica_6').faltante).toBe(null);
  });
});

describe('la mitad agregada se amuebla', () => {
  const variantes = Object.entries(PLANTILLAS).filter(([n]) => /_\d+$/.test(n));

  it('una sala más grande tiene MÁS muebles, no los mismos repartidos', () => {
    // Estirar la fila y correr lo de la derecha deja en medio una franja de
    // suelo pelado del ancho de los puestos nuevos: se lee como un depósito.
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      expect(p.mobiliario.length, nombre).toBeGreaterThan(base.mobiliario.length);
    }
  });

  it('ningún mueble queda fuera de la sala', () => {
    for (const [nombre, p] of variantes) {
      for (const m of p.mobiliario) {
        if (typeof m.gx !== 'number') continue;
        expect(m.gx, `${nombre}/${m.tipo}`).toBeGreaterThanOrEqual(-0.5);
        expect(m.gx, `${nombre}/${m.tipo}`).toBeLessThanOrEqual(p.mundo.ancho);
      }
    }
  });

  it('lo ÚNICO no se duplica: un dispensador no se vuelve tres', () => {
    // Dos dispensadores en una sala no son más sala. Sólo se repite lo que ya
    // se repite a lo largo de una oficina: estanterías y plantas.
    const unicos = ['dispensador', 'mostrador', 'armario', 'panel_fibra', 'tablero'];
    for (const [nombre, p] of variantes) {
      const base = PLANTILLAS[nombre.replace(/_\d+$/, '')];
      for (const tipo of unicos) {
        const antes = base.mobiliario.filter((m) => m.tipo === tipo).length;
        const ahora = p.mobiliario.filter((m) => m.tipo === tipo).length;
        expect(ahora, `${nombre}/${tipo}`).toBe(antes);
      }
    }
  });

  it('ningún mueble repetido cae encima de otro', () => {
    for (const [nombre, p] of variantes) {
      const puntos = p.mobiliario
        .filter((m) => typeof m.gx === 'number' && typeof m.gy === 'number')
        .map((m) => `${m.tipo}|${m.gx}|${m.gy}`);
      expect(new Set(puntos).size, nombre).toBe(puntos.length);
    }
  });
});

describe('cada área se reconoce por lo que tiene dentro', () => {
  /** Los tipos de mueble de una plantilla, sin contar los que lleva cualquiera. */
  const COMUNES = new Set(['zona', 'luminaria', 'planta', 'dispensador', 'mampara', 'ducto']);
  const senas = (p) =>
    [...new Set(p.mobiliario.map((m) => m.tipo))].filter((t) => !COMUNES.has(t)).sort();

  const BASES = ['operaciones', 'atencion', 'tecnica', 'expedientes', 'comercial', 'reuniones'];

  it('el mueble de documentos no está en casi todas las áreas', () => {
    //  LA PREGUNTA QUE ESTA GUARDA NO SABÍA HACER. La de más abajo comprueba
    //  que no haya DOS áreas amuebladas igual, y pasaba en verde mientras la
    //  estantería de carpetas estaba en **6 de 7 plantillas**: cada área era
    //  distinta de las demás por otras piezas, y aun así todas se veían como
    //  un archivo. «¿Por qué todas las oficinas tienen mueble de documento?».
    //
    //  Afirma sobre la pieza más reconocible del catálogo —cuatro baldas de
    //  carpetas de colores— y no sobre el mobiliario en bloque.
    const todas = [...BASES, 'generica'];
    const conEstante = todas.filter((n) =>
      PLANTILLAS[n].mobiliario.some((m) => m.tipo === 'estanteria'));
    expect(conEstante.length, `estantería en ${conEstante.join(', ')}`)
      .toBeLessThanOrEqual(Math.floor(todas.length / 3));
  });

  it('y donde está, está porque el trabajo son los expedientes', () => {
    const cuantas = (n) =>
      PLANTILLAS[n].mobiliario.filter((m) => m.tipo === 'estanteria').length;
    for (const otra of BASES.filter((n) => n !== 'expedientes')) {
      expect(cuantas('expedientes'), `${otra} tiene tantas como expedientes`)
        .toBeGreaterThan(cuantas(otra));
    }
  });

  it('ninguna sala se queda sin mobiliario propio de su oficio', () => {
    //  Todas tenían estantería y planta, así que una de ventas se veía igual
    //  que una de auditoría. El veredicto del 01/11/2026 fue «solo veo cuartos
    //  separados», y esto es la mitad del motivo: no era que faltaran muebles,
    //  era que eran los MISMOS muebles.
    for (const nombre of BASES) {
      expect(senas(PLANTILLAS[nombre]), `${nombre} sin nada propio`).not.toEqual([]);
    }
  });

  it('y dos áreas distintas no se amueblan igual', () => {
    //  La prueba que importa: si dos plantillas tienen las mismas señas, en la
    //  sede se ven como la misma sala con otro nombre.
    const vistas = new Map();
    for (const nombre of BASES) {
      const clave = senas(PLANTILLAS[nombre]).join('+');
      expect(vistas.has(clave),
        `${nombre} se amuebla igual que ${vistas.get(clave)}: ${clave}`).toBe(false);
      vistas.set(clave, nombre);
    }
  });

  it('la sala de redes es la que más equipo técnico tiene', () => {
    //  Tenía UNA estantería y nada más —menos equipo que la sala de
    //  expedientes— y el panel de fibra se lo llevaba Operaciones de Campo.
    const tecnico = (p) =>
      p.mobiliario.filter((m) => ['panel_fibra', 'tablero', 'ducto'].includes(m.tipo)).length;
    expect(tecnico(PLANTILLAS.tecnica)).toBeGreaterThan(1);
  });

  it('el área comercial tiene tableros: es lo que se mira en ventas', () => {
    expect(PLANTILLAS.comercial.mobiliario.filter((m) => m.tipo === 'tablero').length)
      .toBeGreaterThan(1);
  });

  it('ningún mueble de pared se apila con otro en el mismo tramo', () => {
    //  Los muebles de pared se colocan por `gy` y ocupan `largo`. Tres en el
    //  mismo punto dibujan uno, y la sala muestra menos de lo que tiene: pasó
    //  en `generica` al amueblarla, con un tablero, dos estanterías y un
    //  armario casi en el mismo sitio.
    //  Cuánto ocupa cada uno a lo largo del muro, LEÍDO DEL DIBUJO y no
    //  supuesto: el tablero arranca medio paso antes de su `gy` y mide 2,74;
    //  el panel de fibra, 2,1; el armario, 1,5; la estantería, su `largo`.
    //  Con un número inventado esta prueba acusaría solapes que no existen y
    //  dejaría pasar los que sí.
    const DE_PARED = {
      tablero: { antes: 0.12, largo: 2.74 },
      panel_fibra: { antes: 0, largo: 2.1 },
      armario: { antes: 0, largo: 1.5 },
      estanteria: { antes: 0, largo: null }
    };
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      const enLaPared = p.mobiliario
        .filter((m) => DE_PARED[m.tipo])
        .map((m) => {
          const d = DE_PARED[m.tipo];
          const desde = (m.gy ?? 0) - d.antes;
          return { tipo: m.tipo, desde, hasta: desde + (d.largo ?? m.largo ?? 2) };
        })
        .sort((a, b) => a.desde - b.desde);
      for (let i = 1; i < enLaPared.length; i++) {
        expect(enLaPared[i].desde,
          `${nombre}: ${enLaPared[i].tipo} se monta sobre ${enLaPared[i - 1].tipo}`
        ).toBeGreaterThanOrEqual(enLaPared[i - 1].hasta - 0.01);
      }
    }
  });
});

describe('dos muebles de suelo no ocupan el mismo sitio', () => {
  /**
   * Lo que ocupa cada mueble de suelo alrededor de su punto, medido del
   * dibujo. No es exacto —un banco no es un círculo— y es a propósito: una
   * cota generosa caza el solape antes de que se vea, y afinarla pediría
   * replicar la geometría de `oficina.ts` acá, que sería probar la copia.
   */
  //  La luminaria NO entra: va en el techo. Una lámpara sobre un escritorio no
  //  es un choque, es lo que se quiere —y contarla acusaba cuarenta y ocho
  //  solapes que no existen, que es la forma más rápida de que una guarda se
  //  aprenda a ignorar—.
  const RADIO = {
    mostrador: 1.6, mesa: 1.2, banco: 0.7, dispensador: 0.6, planta: 0.5
  };

  it('ninguno cae encima de otro, en ninguna plantilla', () => {
    const choques = [];
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      const suelo = p.mobiliario.filter(
        (m) => RADIO[m.tipo] !== undefined && typeof m.gx === 'number');
      for (let i = 0; i < suelo.length; i++) {
        for (let j = i + 1; j < suelo.length; j++) {
          const a = suelo[i];
          const b = suelo[j];
          const minimo = RADIO[a.tipo] + RADIO[b.tipo];
          if (minimo === 0) continue;
          const d = Math.hypot((a.gx ?? 0) - (b.gx ?? 0), (a.gy ?? 0) - (b.gy ?? 0));
          if (d < minimo) {
            choques.push(`${nombre}: ${a.tipo}@${a.gx},${a.gy} y ${b.tipo}@${b.gx},${b.gy} a ${d.toFixed(1)}`);
          }
        }
      }
    }
    expect(choques).toEqual([]);
  });

  it('y ninguno se sienta encima de un puesto', () => {
    //  Un mueble sobre un escritorio tapa a quien trabaja ahí, que es el único
    //  elemento de la sala que no es decoración.
    const choques = [];
    for (const [nombre, p] of Object.entries(PLANTILLAS)) {
      for (const m of p.mobiliario) {
        if (RADIO[m.tipo] === undefined || typeof m.gx !== 'number') continue;
        for (const q of p.puestos) {
          const d = Math.hypot(m.gx - q.gx, (m.gy ?? 0) - q.gy);
          if (d < RADIO[m.tipo] + 1.1) {
            choques.push(`${nombre}: ${m.tipo}@${m.gx},${m.gy} sobre ${q.id} a ${d.toFixed(1)}`);
          }
        }
      }
    }
    expect(choques).toEqual([]);
  });
});
