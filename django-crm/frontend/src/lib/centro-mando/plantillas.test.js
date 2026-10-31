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
