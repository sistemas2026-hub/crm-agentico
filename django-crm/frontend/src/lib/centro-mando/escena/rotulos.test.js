import { describe, it, expect } from 'vitest';
import { anclaDelNombre, separarRotulos } from './rotulos';

/**
 * La cascada real: once rótulos de sala bajando en diagonal, con las medidas
 * que da el navegador en la vista de conjunto (cuerpo 10, placa de 17 px de
 * alto). Los saltos de 12 px entre anclas son los que producen el choque.
 */
function cascada() {
  /** @type {[string, number][]} */
  const nombres = [
    ['NOC y Redes', 70], ['Dirección', 62], ['Operaciones de Campo', 130],
    ['Sala de Reuniones', 108], ['Atención al Cliente', 118],
    ['Finanzas y Cartera', 112], ['Comercial y Marketing', 136],
    ['Administración', 92], ['Recursos Humanos', 110],
    ['Auditoría y Cumplimiento', 150], ['Recepción', 66]
  ];
  return nombres.map(([, ancho], i) => ({
    x: 600 + i * 34,
    y: 300 + i * 12,
    ancho,
    alto: 17
  }));
}

/** ¿Estas dos placas comparten píxeles? */
function seCruzan(a, b, ya, yb) {
  const enX = a.x < b.x + b.ancho && b.x < a.x + a.ancho;
  const enY = Math.abs(ya - yb) < (a.alto + b.alto) / 2;
  return enX && enY;
}

describe('separar los rótulos que se pisan', () => {
  it('la cascada SIN separar se pisa: si no, esta prueba no mira nada', () => {
    const cajas = cascada();
    let choques = 0;
    for (let i = 0; i < cajas.length; i++)
      for (let j = i + 1; j < cajas.length; j++)
        if (seCruzan(cajas[i], cajas[j], cajas[i].y, cajas[j].y)) choques++;
    expect(choques).toBeGreaterThan(0);
  });

  it('después de separar no queda ningún cruce', () => {
    const cajas = cascada();
    const ys = separarRotulos(cajas);
    for (let i = 0; i < cajas.length; i++)
      for (let j = i + 1; j < cajas.length; j++)
        expect(
          seCruzan(cajas[i], cajas[j], ys[i], ys[j]),
          `${i} contra ${j}`
        ).toBe(false);
  });

  it('ninguno SUBE: un nombre que sube se acerca a la sala de encima', () => {
    const cajas = cascada();
    const ys = separarRotulos(cajas);
    cajas.forEach((c, i) => expect(ys[i]).toBeGreaterThanOrEqual(c.y));
  });

  it('dos placas lejos en X no se mueven aunque estén a la misma altura', () => {
    const cajas = [
      { x: 0, y: 100, ancho: 80, alto: 17 },
      { x: 400, y: 100, ancho: 80, alto: 17 }
    ];
    expect(separarRotulos(cajas)).toEqual([100, 100]);
  });

  it('una sola placa se queda donde está', () => {
    expect(separarRotulos([{ x: 0, y: 42, ancho: 80, alto: 17 }])).toEqual([42]);
  });

  it('es determinista: el mismo orden de entrada da el mismo resultado', () => {
    const a = separarRotulos(cascada());
    const b = separarRotulos(cascada());
    expect(a).toEqual(b);
  });

  it('dos anclas en el MISMO punto se separan en vez de superponerse', () => {
    const cajas = [
      { x: 10, y: 200, ancho: 90, alto: 17 },
      { x: 10, y: 200, ancho: 90, alto: 17 }
    ];
    const ys = separarRotulos(cajas);
    expect(Math.abs(ys[0] - ys[1])).toBeGreaterThanOrEqual(17);
  });

  it('el desplazamiento es el menor que despeja, no un reparto cómodo', () => {
    //  Dos que se tocan por 5 px: el segundo baja esos 5 y la holgura, nada más.
    const cajas = [
      { x: 0, y: 100, ancho: 80, alto: 20 },
      { x: 0, y: 115, ancho: 80, alto: 20 }
    ];
    const ys = separarRotulos(cajas, 2);
    expect(ys[0]).toBe(100);
    expect(ys[1]).toBe(122);
  });
});

describe('el nombre de la sala no cae encima de una placa de puesto', () => {
  //  LA GUARDA QUE FALTABA, y la escribo con el error a la vista: mi prueba de
  //  solapes comparaba nombres de sala contra nombres de sala y decia CERO
  //  choques, mientras 6 de los 11 nombres estaban tapados por la placa de un
  //  escritorio. Medi el par que se me ocurrio y no el que estaba roto.
  const aPantallaX = (gx, gy) => (gx - gy) * 32;
  const aPantallaY = (gx, gy, gz = 0) => (gx + gy) * 16 - gz * 26;

  /** La holgura del nombre de una sala a la placa mas cercana, en pixeles. */
  const holgura = (ancho, fondo, puestos, gx) => {
    const x = aPantallaX(gx, fondo + 0.6);
    const y = aPantallaY(gx, fondo + 0.6);
    let d = Infinity;
    for (const p of puestos) {
      d = Math.min(d, Math.hypot(
        (x - aPantallaX(p.gx ?? 0, p.gy ?? 0)) * 0.55,
        y - aPantallaY(p.gx ?? 0, p.gy ?? 0, 2.6)));
    }
    return d;
  };

  const SALAS = [
    { nombre: 'operaciones', ancho: 14, fondo: 10,
      puestos: [{ gx: 4.8, gy: 7.4 }, { gx: 1.5, gy: 3.4 }, { gx: 4.5, gy: 3.4 }, { gx: 7.5, gy: 3.4 }] },
    { nombre: 'atencion', ancho: 13, fondo: 9,
      puestos: [{ gx: 2.4, gy: 6.0 }, { gx: 1.4, gy: 2.6 }, { gx: 4.6, gy: 2.6 }, { gx: 7.2, gy: 4.6 }] },
    { nombre: 'tecnica', ancho: 11, fondo: 8,
      puestos: [{ gx: 3.4, gy: 5.4 }, { gx: 1.6, gy: 2.4 }, { gx: 5.4, gy: 2.4 }] },
    { nombre: 'reuniones', ancho: 12, fondo: 9,
      puestos: [{ gx: 2.0, gy: 6.0 }, { gx: 2.2, gy: 2.4 }] }
  ];

  it('el ancla elegida deja mas holgura que la esquina', () => {
    for (const s of SALAS) {
      const enLaEsquina = holgura(s.ancho, s.fondo, s.puestos, 0.4);
      const elegida = holgura(s.ancho, s.fondo, s.puestos,
                              anclaDelNombre(s.ancho, s.fondo, s.puestos));
      expect(elegida, `${s.nombre}: esquina ${enLaEsquina.toFixed(0)}px, elegida ${elegida.toFixed(0)}px`)
        .toBeGreaterThanOrEqual(enLaEsquina);
    }
  });

  it('y deja al nombre lejos de toda placa', () => {
    //  Una placa mide unos 26 px de alto. Treinta es un nombre que se lee
    //  entero.
    for (const s of SALAS) {
      const d = holgura(s.ancho, s.fondo, s.puestos,
                        anclaDelNombre(s.ancho, s.fondo, s.puestos));
      expect(d, `${s.nombre}: el nombre queda a ${d.toFixed(0)}px de una placa`)
        .toBeGreaterThan(30);
    }
  });

  it('el ancla nunca se sale de la sala', () => {
    for (const s of SALAS) {
      const gx = anclaDelNombre(s.ancho, s.fondo, s.puestos);
      expect(gx).toBeGreaterThanOrEqual(0);
      expect(gx).toBeLessThanOrEqual(s.ancho - 2);
    }
  });

  it('una sala sin puestos ancla en su esquina', () => {
    expect(anclaDelNombre(12, 9, [])).toBe(0.4);
  });
});
