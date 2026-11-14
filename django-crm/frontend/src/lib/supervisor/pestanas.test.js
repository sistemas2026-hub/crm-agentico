import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { PESTANAS_NOC } from './pestanas.js';
import { gruposDelMenu, estaActiva } from '$lib/v2/menu.js';

/**
 * LAS SUBPANTALLAS DE SUPERVISOR NOC SON UNA SOLA LISTA (28/10/2026), Y DESDE
 * EL 13/11/2026 VIVEN EN EL MENÚ LATERAL.
 *
 * Primero estaban copiadas a mano en cada pantalla y se desordenaron. Después
 * fueron una fila de píldoras en cada encabezado, y tocar «Supervisor» en el
 * menú abría Pendientes —la más pesada— aunque uno fuera a otra. El usuario
 * pidió que al tocar «Supervisor» se desplieguen y se puedan contraer. Estas
 * guardas miran el EFECTO: que el menú las tenga todas, en su orden, que marque
 * la correcta, y que ninguna pantalla vuelva a dibujar su propia fila.
 */
const RUTA = 'src/routes/(app)/supervisor-noc';
const PANTALLAS = [
  '+page.svelte',
  'cuadrillas/+page.svelte',
  'despacho/+page.svelte',
  'programacion/+page.svelte',
  'planes-semanales/+page.svelte',
  'plantillas/+page.svelte',
  'ajustes/+page.svelte',
  'fallas/+page.svelte'
];

const supervisor = () =>
  gruposDelMenu({ role: 'SUPERVISOR' })
    .flatMap((g) => g.items)
    .find((i) => i.href === '/supervisor-noc');

describe('las subpantallas de Supervisor NOC', () => {
  it('Programación va después de Despacho, Fallas de red junto a lo que hay que revisar, y están todas', () => {
    expect(PESTANAS_NOC.map((p) => p.id)).toEqual([
      'pendientes',
      'fallas',
      'cuadrillas',
      'despacho',
      'programacion',
      'plantillas',
      'ajustes'
    ]);
  });

  it('el menú las despliega bajo «Supervisor», en ese orden y con sus rutas', () => {
    const entrada = supervisor();
    expect(entrada?.hijos?.map((h) => h.href)).toEqual(PESTANAS_NOC.map((p) => p.href));
    expect(entrada?.hijos?.[0]?.label).toBe('Pendientes');
  });

  it('la insignia de órdenes detenidas acompaña a Pendientes', () => {
    expect(supervisor()?.hijos?.find((h) => h.href === '/supervisor-noc')?.count).toBe('supervisor');
  });

  it('cada ruta marca UNA sola subpantalla, y Planes semanales cuenta como Programación', () => {
    const hijos = supervisor()?.hijos ?? [];
    const activas = (ruta) => hijos.filter((h) => estaActiva(h, ruta)).map((h) => h.href);
    expect(activas('/supervisor-noc')).toEqual(['/supervisor-noc']);
    expect(activas('/supervisor-noc/despacho')).toEqual(['/supervisor-noc/despacho']);
    expect(activas('/supervisor-noc/planes-semanales')).toEqual(['/supervisor-noc/programacion']);
    expect(activas('/conversaciones')).toEqual([]);
  });

  it('el padre está activo en cualquiera de sus subpantallas y en ninguna otra', () => {
    const entrada = supervisor();
    for (const p of PESTANAS_NOC) expect(estaActiva(entrada, p.href)).toBe(true);
    expect(estaActiva(entrada, '/supervisor-nocturno')).toBe(false);
    expect(estaActiva(entrada, '/')).toBe(false);
  });

  for (const archivo of PANTALLAS) {
    it(`${archivo} no dibuja su propia fila de subpantallas`, () => {
      const fuente = readFileSync(`${RUTA}/${archivo}`, 'utf8');
      expect(fuente).not.toMatch(/PestanasNoc/);
      //  Una pestaña a mano es una píldora con la ruta Y el texto de una
      //  subpantalla. «Ver programación» desde un bloque, o «← Volver a
      //  Programación», no lo son.
      for (const p of PESTANAS_NOC) {
        const a_mano = new RegExp(`snoc-pildora[^"]*" href="${p.href}">\\s*${p.texto}\\s*<`);
        expect(fuente).not.toMatch(a_mano);
      }
    });
  }
});
