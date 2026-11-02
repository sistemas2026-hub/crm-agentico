import { describe, it, expect } from 'vitest';
import { sedeDe } from './sede.js';
import { PLANTILLAS } from './plantillas.js';
import { CELDA, camino, celdaDe, llegadaA, rejillaDe, transitable } from './navegacion.js';
import {
  ESPERA, PASEANDO_A_LA_VEZ, TRANSICION, VELOCIDAD,
  avanzar, crearPaseo, enPie, mezcla, puedeArrancar, puntoEnRuta
} from './paseo.js';

/**
 * EL PASEO, Y LA LÍNEA QUE NO PUEDE CRUZAR.
 *
 * Que un personaje se levante y camine es fácil de ver; lo que hay que medir
 * es lo otro:
 *
 *   - que el paseo NO sea actividad laboral, ni la parezca;
 *   - que el cuerpo no atraviese un muro ni un escritorio en ningún instante
 *     del recorrido, no sólo en los extremos;
 *   - que no se teletransporte;
 *   - y que si la ruta deja de valer, se detenga en vez de seguir.
 */

const BASES = Object.keys(PLANTILLAS).filter((n) => !/_\d+$/.test(n) && n !== 'generica');
const salasDe = (n) => Array.from({ length: n }, (_, i) => {
  const plantilla = BASES[i % BASES.length];
  return {
    id: `d${i}`, rotulo: `Departamento ${i}`, tipo: 'departamento', piso: 1,
    plantilla, planta: PLANTILLAS[plantilla]
  };
});

/** Una sede de verdad con su rejilla, para caminarla. */
function escenario() {
  const sede = sedeDe(salasDe(11), []);
  const rejilla = rejillaDe(sede);
  const patio = sede.plantas.find((p) => p.papel === 'circulacion' && p.mundo.fondo > 20);
  const idPuesto = [...rejilla.destinos.keys()][0];
  const silla = llegadaA(rejilla, idPuesto);
  //  Un punto del pasillo, a media altura del patio.
  const destino = celdaDe(
    patio.origen.gx + patio.mundo.ancho / 2,
    patio.origen.gy + patio.mundo.fondo / 2);
  const ida = camino(rejilla, silla, destino);
  return {
    sede, rejilla, idPuesto,
    mundo: { celda: CELDA, planear: () => (ida ? { ida, vuelta: [...ida].reverse() } : null) }
  };
}

/** Corre un paseo entero y devuelve todo lo que pasó. */
function recorrer(mundo, pasos = 4000, dt = 0.05) {
  let p = crearPaseo('d0:principal', 3);
  //  Se le quita la espera inicial: lo que se mide es el ciclo, no el reloj.
  p = { ...p, espera: 0 };
  const historia = [];
  for (let i = 0; i < pasos; i++) {
    p = avanzar(p, dt, mundo);
    historia.push(p);
    if (historia.length > 10 && p.estado === 'sentado'
        && historia.some((h) => h.estado === 'volviendo')) break;
  }
  return historia;
}

describe('el ciclo completo: levantarse, caminar, volver y sentarse', () => {
  it('pasa por los cinco estados y termina sentado', () => {
    const { mundo } = escenario();
    const h = recorrer(mundo);
    const vistos = [...new Set(h.map((p) => p.estado))];
    for (const e of ['levantandose', 'yendo', 'volviendo', 'sentandose', 'sentado']) {
      expect(vistos, `nunca pasó por «${e}»`).toContain(e);
    }
    expect(h[h.length - 1].estado).toBe('sentado');
  });

  it('vuelve a su puesto, no a cualquier sitio', () => {
    //  «Regreso correcto al puesto». Termina donde empezó.
    const { mundo } = escenario();
    const h = recorrer(mundo);
    const enCamino = h.filter((p) => p.donde);
    expect(enCamino.length).toBeGreaterThan(20);
    const inicio = enCamino[0].donde;
    const ultimo = enCamino[enCamino.length - 1].donde;
    expect(Math.hypot(ultimo.gx - inicio.gx, ultimo.gy - inicio.gy),
      'no volvió a su sitio').toBeLessThan(1.0);
  });

  it('mientras está sentado no tiene cuerpo fuera de la silla', () => {
    const { mundo } = escenario();
    for (const p of recorrer(mundo)) {
      if (p.estado === 'sentado') expect(p.donde).toBe(null);
    }
  });
});

describe('no atraviesa nada, en ningún instante del recorrido', () => {
  it('cada posición del cuerpo cae en una celda transitable', () => {
    //  LA PRUEBA QUE IMPORTA. No alcanza con que los extremos de la ruta sean
    //  válidos: se mira DÓNDE ESTÁ EL CUERPO en cada paso de la simulación,
    //  que es lo que se ve.
    const { rejilla, mundo } = escenario();
    let fuera = 0;
    let peor = null;
    for (const p of recorrer(mundo)) {
      if (!p.donde) continue;
      const c = celdaDe(p.donde.gx, p.donde.gy);
      if (!transitable(rejilla, c.cx, c.cy)) {
        fuera++;
        peor = `${p.estado} en (${p.donde.gx.toFixed(1)}, ${p.donde.gy.toFixed(1)})`;
      }
    }
    expect(fuera, `${fuera} posiciones fuera de lo transitable, p.ej. ${peor}`).toBe(0);
  });

  it('y no se teletransporta: cada paso es un paso', () => {
    //  A 1,5 por segundo y 0,05 de paso, el cuerpo avanza 0,075. Un salto de
    //  más de una celda es un parpadeo, y a esta escala se nota.
    const { mundo } = escenario();
    const h = recorrer(mundo).filter((p) => p.donde);
    for (let i = 1; i < h.length; i++) {
      const d = Math.hypot(h[i].donde.gx - h[i - 1].donde.gx,
                           h[i].donde.gy - h[i - 1].donde.gy);
      expect(d, `salto de ${d.toFixed(2)} en el paso ${i} (${h[i].estado})`)
        .toBeLessThan(VELOCIDAD * 0.05 + 0.3);
    }
  });

  it('si la ruta deja de valer, se sienta en vez de seguir', () => {
    //  Lo que no puede pasar nunca es que siga avanzando sobre un camino que
    //  ya no existe: ahí es donde alguien cruza una pared.
    let p = crearPaseo('x', 1);
    p = avanzar({ ...p, espera: 0 }, 0.05, {
      celda: CELDA,
      planear: () => ({ ida: [{ cx: 0, cy: 0 }, { cx: 1, cy: 0 }, { cx: 2, cy: 0 }], vuelta: [] })
    });
    //  Se le rompe la ruta a mitad de camino.
    p = { ...p, estado: 'yendo', ruta: null };
    p = avanzar(p, 0.05, { celda: CELDA, planear: () => null });
    expect(p.estado).toBe('sentandose');
  });

  it('sin ruta posible no se levanta', () => {
    const p = avanzar({ ...crearPaseo('x', 1), espera: 0 }, 0.05,
                      { celda: CELDA, planear: () => null });
    expect(p.estado).toBe('sentado');
    expect(p.donde).toBe(null);
  });
});

describe('un paseo no es actividad laboral, y no puede parecerlo', () => {
  it('lleva su procedencia escrita en el dato', () => {
    //  No en un comentario: quien reciba esto tiene que poder decir que es
    //  ambiente sin preguntarle a nadie.
    expect(crearPaseo('d0:p1', 7).procedencia).toBe('ambiente');
    const { mundo } = escenario();
    for (const p of recorrer(mundo)) expect(p.procedencia).toBe('ambiente');
  });

  it('no trae agente, ni área, ni herramienta, ni estado de ejecución', () => {
    const { mundo } = escenario();
    for (const p of recorrer(mundo)) {
      for (const campo of ['agente', 'area', 'herramienta', 'ejecucion',
                           'actividad', 'evento', 'ticket', 'nombre']) {
        expect(p[campo], `un paseo trae «${campo}»`).toBeUndefined();
      }
    }
  });

  it('lo único que sabe de quién pasea es su identificador de puesto', () => {
    //  `crearPaseo` recibe dos cosas y ninguna es un dato de la empresa.
    expect(crearPaseo.length).toBe(2);
    expect(crearPaseo('d0:p1', 7).puesto).toBe('d0:p1');
  });
});

describe('no todos a la vez, y no siempre', () => {
  it('como mucho uno caminando', () => {
    const quietos = [crearPaseo('a', 1), crearPaseo('b', 2)];
    expect(puedeArrancar(quietos)).toBe(true);
    const unoEnPie = [{ ...crearPaseo('a', 1), estado: 'yendo' }, crearPaseo('b', 2)];
    expect(puedeArrancar(unoEnPie)).toBe(PASEANDO_A_LA_VEZ > 1);
  });

  it('cada uno arranca con su propia espera', () => {
    const esperas = new Set([1, 2, 3, 4, 5].map((s) => crearPaseo('x', s).espera.toFixed(3)));
    expect(esperas.size).toBeGreaterThan(3);
  });

  it('la espera entre paseos es larga: no da vueltas', () => {
    for (const s of [1, 5, 9, 13]) {
      const p = crearPaseo('x', s);
      expect(p.espera).toBeGreaterThanOrEqual(ESPERA.minima);
      expect(p.espera).toBeLessThanOrEqual(ESPERA.maxima);
    }
    expect(ESPERA.minima).toBeGreaterThanOrEqual(15);
  });

  it('se ve igual en dos cargas seguidas', () => {
    expect(crearPaseo('x', 9)).toEqual(crearPaseo('x', 9));
  });
});

describe('el cambio entre sentado y de pie no da un salto', () => {
  it('la mezcla va de 0 a 1 y vuelve, sin escalones', () => {
    expect(mezcla({ estado: 'sentado' })).toBe(0);
    expect(mezcla({ estado: 'levantandose', fase: 0 })).toBe(0);
    expect(mezcla({ estado: 'levantandose', fase: TRANSICION })).toBe(1);
    expect(mezcla({ estado: 'yendo' })).toBe(1);
    expect(mezcla({ estado: 'sentandose', fase: 0 })).toBe(1);
    expect(mezcla({ estado: 'sentandose', fase: TRANSICION })).toBe(0);
  });

  it('y crece sin saltos durante la transición', () => {
    //  Arranca en 0 y no en -1: el primer valor de la mezcla ES 0, y comparar
    //  contra -1 daba un salto de 1 que no existe. Error mío de la prueba, no
    //  del código.
    let previo = 0;
    for (let i = 0; i <= 20; i++) {
      const m = mezcla({ estado: 'levantandose', fase: (i / 20) * TRANSICION });
      expect(m).toBeGreaterThanOrEqual(previo);
      expect(m - previo).toBeLessThan(0.2);
      previo = m;
    }
  });

  it('en pie es exactamente mientras está fuera de la silla', () => {
    expect(enPie({ estado: 'sentado' })).toBe(false);
    for (const e of ['levantandose', 'yendo', 'volviendo', 'sentandose']) {
      expect(enPie({ estado: e }), e).toBe(true);
    }
  });
});

describe('puntoEnRuta', () => {
  it('interpola entre dos celdas en vez de saltar', () => {
    const ruta = [{ cx: 0, cy: 0 }, { cx: 4, cy: 0 }];
    const a = puntoEnRuta(ruta, 0, 0.5);
    const b = puntoEnRuta(ruta, 1, 0.5);
    expect(b.gx).toBeGreaterThan(a.gx);
    expect(b.gx - a.gx).toBeCloseTo(1, 5);
    expect(b.gy).toBe(a.gy);
  });

  it('pasado el final se queda en el final, no sigue de largo', () => {
    const ruta = [{ cx: 0, cy: 0 }, { cx: 2, cy: 0 }];
    const fin = puntoEnRuta(ruta, 999, 0.5);
    expect(fin.gx).toBeCloseTo((2 + 0.5) * 0.5, 5);
  });

  it('una ruta vacía no revienta', () => {
    expect(puntoEnRuta([], 1, 0.5)).toBe(null);
    expect(puntoEnRuta(null, 1, 0.5)).toBe(null);
  });
});
