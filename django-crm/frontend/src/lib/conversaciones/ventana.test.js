/**
 * La ventana de 24 h en la cola (29/10/2026).
 *
 * Las negativas son las que importan: sin dato NO es cerrada (no se apura a
 * nadie por algo que no se sabe), y con la IA atendiendo no se marca (no hay
 * persona a quien apurar).
 */
import { describe, it, expect } from 'vitest';
import { restanteDeVentana, ventanaUrge, comoRestante, URGE_DESDE_SEG } from './ventana.js';

const LEIDA = '2026-10-29T20:00:00Z';
const AHORA = Date.parse(LEIDA);

describe('restanteDeVentana', () => {
  it('descuenta lo que pasó desde que se leyó la cola', () => {
    const v = { abierta: true, restante_seg: 3600 };
    expect(restanteDeVentana(v, LEIDA, AHORA + 600_000)).toBe(3000);
  });
  it('no baja de cero', () => {
    expect(restanteDeVentana({ abierta: true, restante_seg: 60 }, LEIDA, AHORA + 3_600_000)).toBe(0);
  });
  it('sin dato no es cerrada: es null', () => {
    expect(restanteDeVentana(null, LEIDA, AHORA)).toBeNull();
    expect(restanteDeVentana({ abierta: null, restante_seg: null }, LEIDA, AHORA)).toBeNull();
  });
  it('cerrada es cero', () => {
    expect(restanteDeVentana({ abierta: false, restante_seg: 0 }, LEIDA, AHORA)).toBe(0);
  });
});

describe('ventanaUrge', () => {
  const humana = { estado: 'abierta', control: 'humano' };
  it('queda poco y le toca a una persona: se marca', () => {
    expect(ventanaUrge(humana, 45 * 60)).toBe(true);
  });
  it('con la IA atendiendo no se marca', () => {
    expect(ventanaUrge({ estado: 'abierta', control: 'ia' }, 45 * 60)).toBe(false);
  });
  it('con más de dos horas no se marca', () => {
    expect(ventanaUrge(humana, URGE_DESDE_SEG + 60)).toBe(false);
  });
  it('cerrada o sin dato no se marca: ya no hay nada que apurar', () => {
    expect(ventanaUrge(humana, 0)).toBe(false);
    expect(ventanaUrge(humana, null)).toBe(false);
  });
  it('mira también las otras abiertas del chat', () => {
    const chat = { estado: 'abierta', control: 'ia', abiertas: [humana] };
    expect(ventanaUrge(chat, 30 * 60)).toBe(true);
  });
});

describe('comoRestante', () => {
  it.each([
    [30, '1 min'],
    [45 * 60, '45 min'],
    [80 * 60, '1 h 20 min'],
    [3 * 3600, '3 h']
  ])('%i s → %s', (seg, texto) => expect(comoRestante(seg)).toBe(texto));
});
