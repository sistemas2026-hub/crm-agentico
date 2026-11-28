/**
 * El deep-link de la Bandeja (12/11/2026): qué valores de `?pestana=` se
 * aceptan, y que una banda filtre por la MISMA columna que contó Hoy.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { intencionDelEnlace, deLaBanda, PESTANAS_DEL_ENLACE } from './enlace.js';
import { PREDICADOS } from './pestanas.js';

const de = (/** @type {string} */ q) => intencionDelEnlace(new URLSearchParams(q));

describe('intencionDelEnlace', () => {
  it('acepta exactamente las pestañas que existen', () => {
    expect([...PESTANAS_DEL_ENLACE].sort()).toEqual([...Object.keys(PREDICADOS), 'todas'].sort());
    for (const p of PESTANAS_DEL_ENLACE) expect(de(`pestana=${p}`)).toEqual({ pestana: p, banda: null, etiqueta: '' });
  });

  it('las bandas de Hoy abren «Todos» filtrado por su número', () => {
    expect(de('pestana=sin_asignar')).toMatchObject({ pestana: 'todas', banda: 2 });
    expect(de('pestana=revisar')).toMatchObject({ pestana: 'todas', banda: 3 });
    expect(de('pestana=cliente_espera')).toMatchObject({ pestana: 'todas', banda: 1 });
    expect(de('pestana=SIN_ASIGNAR ')).toMatchObject({ banda: 2 });
  });

  it('sin parámetro, vacío o desconocido: no pide nada', () => {
    for (const q of ['', 'pestana=', 'pestana=borrar', 'otra=por-atender', 'pestana=__proto__', 'pestana=constructor', 'pestana=tostring']) {
      expect(de(q)).toBeNull();
    }
    expect(intencionDelEnlace(null)).toBeNull();
  });
});

describe('deLaBanda', () => {
  const lista = [{ id: 'a', banda: 2 }, { id: 'b', banda: 3 }, { id: 'c', banda: null }, { id: 'd' }];
  it('deja solo las filas de esa banda', () => {
    expect(deLaBanda(lista, 2).map((c) => c.id)).toEqual(['a']);
  });
  it('sin banda, la lista entera', () => {
    expect(deLaBanda(lista, null)).toBe(lista);
  });
});

describe('el layout lo lee de la URL', () => {
  const layout = readFileSync(new URL('../../../routes/(app)/conversaciones/+layout.svelte', import.meta.url), 'utf-8');
  it('aplica la intención de page.url y filtra la lista por la banda', () => {
    expect(layout).toMatch(/intencionDelEnlace\(page\.url\.searchParams\)/);
    expect(layout).toMatch(/deLaBanda\(/);
  });
});
