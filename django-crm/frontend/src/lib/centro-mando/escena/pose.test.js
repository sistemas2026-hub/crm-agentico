import { describe, it, expect } from 'vitest';
import { ANIMACIONES, POSE_NEUTRA, Transicion, mezclar, poseDe } from './pose';

/**
 * Acá se prueba la animación con números, que es la única forma de probarla en
 * este repositorio: jsdom no arranca (medido el 07/10/2026) y lo que se dibuja
 * solo se puede verificar mirando.
 *
 * Las dos afirmaciones que valen algo:
 *   · los cinco estados se VEN distintos (si dos dieran la misma pose, la
 *     escena diría cinco cosas y mostraría cuatro)
 *   · ninguna transición SALTA (y no hace falta programar veinte, porque la
 *     transición es interpolar)
 */

const CANALES = Object.keys(POSE_NEUTRA);

describe('los cinco estados son cinco', () => {
  it('ninguna pareja produce la misma pose', () => {
    const vistas = new Map();
    for (const a of ANIMACIONES) {
      const firma = JSON.stringify(poseDe(a, 1.3));
      expect(vistas.has(firma), `«${a}» da la misma pose que «${vistas.get(firma)}»`).toBe(false);
      vistas.set(firma, a);
    }
  });

  it('«incognito» NO se parece a «reposo»', () => {
    // Es la razón de ser de todo este trabajo: un agente quieto por no tener
    // trabajo y uno quieto porque su motor murió no pueden verse igual.
    const r = poseDe('reposo', 2);
    const i = poseDe('incognito', 2);
    expect(i.apagado).toBeGreaterThan(0.5);
    expect(r.apagado).toBe(0);
    expect(i.incertidumbre).toBeGreaterThan(0.4);
    expect(r.incertidumbre).toBe(0);
    expect(i.brilloPantalla).toBeLessThan(r.brilloPantalla);
  });

  it('solo «despachar» mueve el paquete', () => {
    for (const a of ANIMACIONES) {
      const p = poseDe(a, 0.9);
      if (a === 'despachar') expect(p.despacho).toBeGreaterThan(0);
      else expect(p.despacho).toBe(0);
    }
  });

  it('«alerta» es la que más halo pide', () => {
    const auras = ANIMACIONES.map((a) => [a, poseDe(a, 1.1).aura]);
    const mayor = auras.sort((x, y) => y[1] - x[1])[0][0];
    expect(mayor).toBe('alerta');
  });
});

describe('la quietud también se anima', () => {
  it('el reposo respira: la pose cambia con el tiempo', () => {
    // Un personaje detenido del todo se lee como una imagen pegada. Es el
    // detalle más barato que separa «escena viva» de «captura».
    const a = poseDe('reposo', 0);
    const b = poseDe('reposo', 0.9);
    expect(a.torsoY).not.toBeCloseTo(b.torsoY, 3);
  });

  it('y respira poco: nada se mueve más de 3 px', () => {
    let maximo = 0;
    for (let t = 0; t < 12; t += 0.05) {
      const p = poseDe('reposo', t);
      maximo = Math.max(maximo, Math.abs(p.torsoY), Math.abs(p.cabezaY));
    }
    expect(maximo).toBeLessThan(3);
  });

  it('las dos manos del tecleo no suben juntas', () => {
    // Si subieran a la vez sería un aplauso, no un tecleo.
    let contrarias = 0;
    for (let t = 0; t < 4; t += 0.02) {
      const p = poseDe('teclear', t);
      if (Math.sign(p.manoIzqY) !== Math.sign(p.manoDerY)) contrarias++;
    }
    expect(contrarias).toBeGreaterThan(150);
  });
});

describe('las transiciones no se programan una por una', () => {
  it('ninguna de las veinte parejas salta', () => {
    // Veinte transiciones posibles. Escribirlas a mano garantiza que cuatro o
    // cinco queden sin hacer, y las que faltan no fallan: saltan.
    const paso = 1 / 60;
    for (const desde of ANIMACIONES) {
      for (const hasta of ANIMACIONES) {
        if (desde === hasta) continue;
        const t = new Transicion(desde);
        const antes = { ...t.avanzar(paso, 1) };
        t.hacia(hasta);
        const despues = t.avanzar(paso, 1 + paso);
        for (const c of CANALES) {
          const salto = Math.abs(despues[c] - antes[c]);
          // En un fotograma, con tau 0.18, se recorre ~8% de la diferencia.
          // Un cambio instantáneo sería el 100%.
          const diferencia = Math.abs(poseDe(hasta, 1 + paso)[c] - antes[c]);
          expect(salto, `${desde}→${hasta} en ${c}`).toBeLessThanOrEqual(diferencia * 0.35 + 0.02);
        }
      }
    }
  });

  it('llega al estado nuevo, no se queda a medias', () => {
    const t = new Transicion('reposo');
    t.hacia('alerta');
    for (let i = 0; i < 120; i++) t.avanzar(1 / 60, 2 + i / 60);
    const fin = t.actual;
    const objetivo = poseDe('alerta', 2 + 120 / 60);
    expect(fin.aura).toBeCloseTo(objetivo.aura, 1);
    expect(fin.torsoInclina).toBeCloseTo(objetivo.torsoInclina, 2);
  });

  it('repetir el mismo estado no reinicia nada', () => {
    const t = new Transicion('reposo');
    t.hacia('teclear');
    for (let i = 0; i < 10; i++) t.avanzar(1 / 60, i / 60);
    const medio = { ...t.actual };
    t.hacia('teclear');
    const siguiente = t.avanzar(1 / 60, 11 / 60);
    expect(Math.abs(siguiente.torsoInclina - medio.torsoInclina)).toBeLessThan(0.02);
  });

  it('un salto de tiempo enorme no descoloca la figura', () => {
    // Al volver de una pestaña oculta el navegador entrega un `dt` enorme.
    const t = new Transicion('reposo');
    t.hacia('despachar');
    const p = t.avanzar(30, 40);
    for (const c of CANALES) expect(Number.isFinite(p[c])).toBe(true);
  });
});

describe('mezclar', () => {
  it('con k 0 y 1 devuelve los extremos', () => {
    const a = poseDe('reposo', 1);
    const b = poseDe('alerta', 1);
    expect(mezclar(a, b, 0)).toEqual(a);
    expect(mezclar(a, b, 1)).toEqual(b);
  });

  it('acota k fuera de rango en vez de extrapolar', () => {
    // Extrapolar con k 2 produciría poses imposibles —un torso 30 px bajo el
    // asiento— ante un `dt` raro.
    const a = poseDe('reposo', 1);
    const b = poseDe('alerta', 1);
    expect(mezclar(a, b, 5)).toEqual(b);
    expect(mezclar(a, b, -3)).toEqual(a);
  });

  it('mezcla TODOS los canales, no los que alguien se acordó de poner', () => {
    const a = { ...POSE_NEUTRA };
    const b = {};
    for (const c of CANALES) b[c] = 10;
    const m = mezclar(a, b, 0.5);
    for (const c of CANALES) expect(m[c]).toBeCloseTo((a[c] + 10) / 2, 6);
  });
});
