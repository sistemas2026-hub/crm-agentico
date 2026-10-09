import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import SistemasExternos from './SistemasExternos.svelte';

const ms = (v) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);
const pinta = (servicios, props = {}) =>
  render(SistemasExternos, { props: { servicios, ms, ...props } }).body;

const VERDE = '#15803D', AMBAR = '#A15C07', ROJO = '#B91C1C';

describe('la franja de sistemas externos', () => {
  it('sin servicios no dibuja nada', () => {
    // Un tenant recien dado de alta no ha usado ninguna herramienta todavia.
    expect(pinta([])).not.toContain('Sistemas');
    expect(pinta(null)).not.toContain('Sistemas');
  });

  it('nombra cada sistema con sus usos', () => {
    const b = pinta([{ herramienta: 'consultar_olt', usos: 31, fallos: 0, duracion_media_ms: 687 }]);
    expect(b).toContain('consultar_olt');
    expect(b).toContain('31 usos');
    expect(b).toContain('687 ms');
  });

  it('acota cuantos muestra', () => {
    const muchos = Array.from({ length: 12 }, (_, i) => ({ herramienta: `h_${i}`, usos: 5, fallos: 0 }));
    const b = pinta(muchos, { maximo: 4 });
    expect(b).toContain('h_3');
    expect(b).not.toContain('h_4');
  });
});

describe('la salud se juzga por TASA, no por cuenta', () => {
  it('sin fallos, responde', () => {
    expect(pinta([{ herramienta: 'a', usos: 40, fallos: 0 }])).toContain(VERDE);
  });

  it('dos fallos de dos es un sistema caido', () => {
    // Es la distincion que esta franja existe para soportar: dos fallos de
    // dos y dos de doscientas no son lo mismo, y la cuenta sola no los separa.
    const b = pinta([{ herramienta: 'a', usos: 2, fallos: 2 }]);
    expect(b).toContain(ROJO);
    expect(b).toContain('fallando');
  });

  it('dos fallos de doscientas es ruido normal', () => {
    const b = pinta([{ herramienta: 'a', usos: 200, fallos: 2 }]);
    expect(b).toContain(AMBAR);
    expect(b).not.toContain(ROJO);
  });

  it('dice cuantos fallaron cuando los hay', () => {
    expect(pinta([{ herramienta: 'a', usos: 10, fallos: 3 }])).toContain('3 fallaron');
  });

  it('un sistema sano no menciona fallos', () => {
    expect(pinta([{ herramienta: 'a', usos: 10, fallos: 0 }])).not.toContain('fallaron');
  });
});

describe('privacidad', () => {
  it('nombra al agente que lo uso, nunca a un cliente', () => {
    // `ultimo_agente` es un rol del tenant, no una persona: el motor no manda
    // nada del cliente en `servicios` (panorama_centro_mando).
    const b = pinta([{
      herramienta: 'consultar_cliente', usos: 9, fallos: 0,
      ultimo_agente: 'soporte_tecnico_cliente',
      telefono: '3001234567'
    }]);
    expect(b).toContain('soporte tecnico cliente');
    expect(b).not.toContain('3001234567');
  });
});
