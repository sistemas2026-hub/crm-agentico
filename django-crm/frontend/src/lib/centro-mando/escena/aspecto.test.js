import { describe, it, expect } from 'vitest';
import { COLOR_DE_ANIMACION, PIEL, PELO, ROPA, aspectoDe, coloresConAcento } from './paleta';
import { salasDe } from '../departamentos.js';
import PORDEFECTO from '../__fixtures__/organizacion-por-defecto.json';

/**
 * QUE DOS AGENTES NO SEAN LA MISMA PERSONA, Y QUE UN ROJO SIGA SIENDO UN ROJO.
 *
 * Dos cosas distintas que se construyeron juntas y conviene no confundir:
 *
 *   el ASPECTO varía por AGENTE   — ropa, pelo, piel
 *   el ACENTO varía por SALA      — la luz, el cartel, el halo de reposo
 *
 * Y una regla que las separa de todo lo demás: **el acento tiñe la sala, nunca
 * los estados**. Si el rojo de un fallo cambiara de departamento en
 * departamento, quien mira dos pantallas aprendería que el color no quiere
 * decir nada — y entonces no serviría en ninguna.
 */

describe('el aspecto es estable', () => {
  it('el mismo agente en el mismo asiento se ve igual dos veces', () => {
    // Si fuera azar, cambiaría de cara cada vez que alguien recarga.
    expect(aspectoDe('supervisor_noc', 2)).toEqual(aspectoDe('supervisor_noc', 2));
  });

  it('nombres parecidos no comparten pelo Y piel a la vez', () => {
    // `atencion_1` y `atencion_2` se sientan uno al lado del otro. La camisa ya
    // los separa por asiento; esto comprueba que la persona también difiere.
    const a = aspectoDe('atencion_1', 0);
    const b = aspectoDe('atencion_2', 0);
    expect(a.pelo !== b.pelo || a.piel !== b.piel).toBe(true);
  });

  it('dos compañeros de sala NUNCA llevan la misma camisa', () => {
    // Por construcción, no por suerte. La primera versión lo dejaba al reparto
    // del hash y esta misma prueba la cazó: de cuatro puestos salían tres
    // aspectos, o sea dos agentes idénticos sentados en la misma sala.
    for (const s of salasDe(PORDEFECTO)) {
      const camisas = s.planta.puestos.map((p, i) => aspectoDe(p.id, i).camisa);
      expect(new Set(camisas).size, s.id).toBe(camisas.length);
    }
  });

  it('y la garantía aguanta hasta llenar la paleta de ropa', () => {
    const camisas = Array.from({ length: ROPA.length }, (_, i) => aspectoDe(`n${i}`, i).camisa);
    expect(new Set(camisas).size).toBe(ROPA.length);
  });

  it('el asiento NO cambia el pelo ni la piel', () => {
    // Si cambiaran, mover a alguien de puesto le cambiaría la cara.
    const a = aspectoDe('supervisor_noc', 0);
    const b = aspectoDe('supervisor_noc', 3);
    expect(b.pelo).toBe(a.pelo);
    expect(b.piel).toBe(a.piel);
  });

  it('sale de la paleta declarada, no de un color inventado', () => {
    const a = aspectoDe('cualquiera', 1);
    expect(ROPA).toContain(a.camisa);
    expect(PELO).toContain(a.pelo);
    expect(PIEL).toContain(a.piel);
  });

  it('la sombra de la camisa se deriva de la camisa', () => {
    // Elegirlas por separado deja a alguien con el costado iluminado al revés.
    const a = aspectoDe('x');
    expect(a.camisaSombra).not.toBe(a.camisa);
    expect(a.camisaSombra).toBeLessThan(0xffffff);
  });

  it('sin nombre no explota: devuelve un aspecto válido', () => {
    for (const malo of ['', null, undefined]) {
      const a = aspectoDe(malo);
      expect(ROPA).toContain(a.camisa);
    }
  });

  it('reparte: veinte nombres no caen todos en el mismo pelo', () => {
    const usados = new Set(
      Array.from({ length: 20 }, (_, i) => aspectoDe(`agente_${i}`).pelo)
    );
    expect(usados.size).toBeGreaterThan(2);
  });
});

describe('el acento tiñe la sala, NUNCA los estados', () => {
  const conAcento = coloresConAcento(0x1f7a6b);

  it('el fallo es el mismo rojo en todas las salas', () => {
    // La afirmación que mata la mutación: si alguien hiciera que `alerta`
    // derivara del acento, esto se pone rojo.
    expect(conAcento.alerta).toBe(COLOR_DE_ANIMACION.alerta);
  });

  it('«no sé» es el mismo gris en todas', () => {
    expect(conAcento.incognito).toBe(COLOR_DE_ANIMACION.incognito);
  });

  it('despachar tampoco cambia', () => {
    expect(conAcento.despachar).toBe(COLOR_DE_ANIMACION.despachar);
  });

  it('pero reposo y trabajando sí toman el acento', () => {
    expect(conAcento.reposo).toBe(0x1f7a6b);
    expect(conAcento.reposo).not.toBe(COLOR_DE_ANIMACION.reposo);
    expect(conAcento.teclear).not.toBe(COLOR_DE_ANIMACION.teclear);
  });

  it('sin acento, todo queda como estaba', () => {
    expect(coloresConAcento(undefined)).toBe(COLOR_DE_ANIMACION);
    expect(coloresConAcento(0)).toBe(COLOR_DE_ANIMACION);
  });
});

describe('cada sala tiene su color, y ninguno choca con una alarma', () => {
  //  LAS SALAS SALEN DE LA CONFIGURACION (31/10/2026). Antes esta guarda
  //  recorria una lista de seis departamentos escrita en el frontend; ahora
  //  recorre las once salas que declara la organizacion de la empresa piloto,
  //  leidas del mismo documento que sirve el motor.
  //
  //  Que la guarda siga siendo util con la lista llegando de fuera es parte de
  //  lo que se compro: el dia que una empresa elija un acento rojizo desde su
  //  configuracion, esto lo encuentra.
  const SALAS = salasDe(PORDEFECTO);

  it('hay salas que vigilar (si no, la guarda no prueba nada)', () => {
    //  Una guarda que recorre una lista vacia pasa siempre, y ahora la lista
    //  viene de un documento externo: si el fixture se vaciara, esta guarda se
    //  volveria decorativa sin que nada se pusiera rojo.
    expect(SALAS.length).toBeGreaterThanOrEqual(8);
  });

  it('todas declaran acento', () => {
    for (const s of SALAS) {
      expect(typeof s.planta.acento, s.id).toBe('number');
    }
  });

  it('no se repiten entre salas', () => {
    const acentos = SALAS.map((s) => s.planta.acento);
    expect(new Set(acentos).size).toBe(acentos.length);
  });

  it('se distinguen entre si de un vistazo', () => {
    // No es la garantia fuerte --esa es la distancia al rojo-- pero dos salas
    // del mismo azul se leerian como la misma.
    const canales = (c) => [(c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff];
    for (const a of SALAS) {
      for (const b of SALAS) {
        if (a === b) continue;
        const [r1, g1, b1] = canales(a.planta.acento);
        const [r2, g2, b2] = canales(b.planta.acento);
        const d = Math.abs(r1 - r2) + Math.abs(g1 - g2) + Math.abs(b1 - b2);
        expect(d, `${a.id} y ${b.id} se parecen`).toBeGreaterThan(70);
      }
    }
  });

  it('ninguno se parece al rojo de un fallo', () => {
    // Un acento rojizo haria que una sala tranquila se leyera como una sala en
    // alarma. Se mide la distancia en los tres canales.
    const canales = (c) => [(c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff];
    const [rr, rg, rb] = canales(COLOR_DE_ANIMACION.alerta);
    for (const s of SALAS) {
      const [r, g, b] = canales(s.planta.acento);
      const distancia = Math.abs(r - rr) + Math.abs(g - rg) + Math.abs(b - rb);
      expect(distancia, `${s.id} se parece demasiado al rojo de alarma`).toBeGreaterThan(160);
    }
  });
});
