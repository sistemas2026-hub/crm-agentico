/**
 * El panel de cierre y la barra de acciones, dibujados de verdad (10/11/2026).
 *
 * Nace de una captura: doce opciones en una grilla que se leía de costado,
 * «Otro» elegido con la nota vacía y el botón de cerrar habilitado, y
 * «Resuelto» solo en una segunda línea debajo del estado. Afirma sobre lo que
 * SALE, no sobre que el mecanismo exista.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import CierrePanel from './CierrePanel.svelte';
import HandoffControls from './HandoffControls.svelte';

const CATALOGO = [
  { codigo: 'equipo_cliente', nombre: 'Equipo del cliente', categoria_base: 'equipo_cliente', origen: 'plataforma', grupo: 'falla', exige_nota: false },
  { codigo: 'red_central', nombre: 'Red central', categoria_base: 'red_central', origen: 'plataforma', grupo: 'falla', exige_nota: false },
  { codigo: 'facturacion', nombre: 'Facturación', categoria_base: 'facturacion', origen: 'plataforma', grupo: 'otra_cosa', exige_nota: false },
  { codigo: 'otro', nombre: 'Otro', categoria_base: 'otro', origen: 'plataforma', grupo: 'otra_cosa', exige_nota: true }
];

const sinMarcas = (/** @type {string} */ html) =>
  html.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

describe('el panel de cierre', () => {
  const html = render(CierrePanel, { props: { catalogo: CATALOGO } }).body;

  it('separa las dos preguntas, cada una con su título y sus opciones', () => {
    const grupos = html.split('<fieldset').slice(1);
    expect(grupos).toHaveLength(2);
    expect(sinMarcas(grupos[0])).toMatch(/Dónde estuvo la falla.*Equipo del cliente.*Red central/);
    expect(sinMarcas(grupos[0])).not.toMatch(/Facturación/);
    expect(sinMarcas(grupos[1])).toMatch(/No era una falla de la red.*Facturación.*Otro/);
  });

  it('ninguna viene elegida, y sin elegir no se puede cerrar', () => {
    expect(html).not.toMatch(/checked/);
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled/);
    expect(sinMarcas(html)).toMatch(/Elegí en qué terminó el caso/);
  });

  it('la consecuencia está junto al botón, no entre las instrucciones', () => {
    const pie = html.slice(html.indexOf('class="pie'));
    expect(sinMarcas(pie)).toMatch(/Se cierra la conversación.*Cerrar el caso/);
    expect(sinMarcas(html.slice(0, html.indexOf('<fieldset')))).not.toMatch(/Se cierra la conversación/);
  });

  it('«Cerrar el caso» lleva el verde del cierre, no la tinta de «Tomar»', () => {
    const boton = html.match(/<button[^>]*type="submit"[^>]*>|<button[^>]*class="[^"]*boton-cerrar[^>]*>/)?.[0] ?? '';
    expect(boton).toMatch(/boton-cerrar/);
    expect(boton).not.toMatch(/v2-btn-ink/);
  });

  it('las opciones son fichas: la radio queda para el teclado, sin el punto a la vista', () => {
    expect(html).toMatch(/class="radio-oculta/);
  });

  it('la nota dice que es opcional mientras no se eligió «Otro»', () => {
    expect(sinMarcas(html)).toMatch(/Nota \(opcional\)/);
    expect(html).not.toMatch(/<textarea[^>]*required/);
  });
});

describe('la barra de acciones mientras se cierra', () => {
  const BASE = /** @type {any} */ ({
    conversacion: { id: 'c1', estado: 'abierta', motivo_escalamiento: 'falla_servicio' },
    caso: null,
    operadores: [],
    iaEnPausa: true, escalada: true, atendida: false, esMia: false, asignadaA: '',
    esAdmin: false, gobernada: true,
    areas: {}
  });
  const dibuja = (/** @type {any} */ props) =>
    render(HandoffControls, { props: { ...BASE, ...props } }).body;

  it('los gestos van juntos en un grupo: no queda uno suelto en otra línea', () => {
    const html = dibuja({});
    const grupo = html.slice(html.indexOf('aviso-acciones'));
    expect(sinMarcas(grupo)).toMatch(/Tomar.*Resuelto/);
  });

  it('«Reasignar» y «Escalar a un área» se ven como botones, no como texto suelto', () => {
    const html = dibuja({ esAdmin: true, operadores: [{ usuario_id: 'u2', nombre: 'Ana' }], areas: { noc: 'NOC' } });
    for (const rotulo of ['Reasignar', 'Escalar a un área']) {
      const i = html.indexOf(rotulo);
      const boton = html.slice(html.lastIndexOf('<button', i), i);
      expect(boton, rotulo).toMatch(/aviso-secundario/);
      expect(boton, rotulo).not.toMatch(/v2-btn-quiet/);
    }
    // Y una línea separa los gestos del relevo de «Resuelto».
    expect(html).toMatch(/aviso-separador/);
  });

  it('sin ningún gesto de relevo antes, no hay línea delante de «Resuelto»', () => {
    expect(dibuja({ escalada: false, iaEnPausa: false })).not.toMatch(/aviso-separador/);
  });

  it('cerrado el panel: «Resuelto» sin apretar y «Tomar» en tinta', () => {
    const html = dibuja({});
    expect(html).toMatch(/aria-expanded="false"/);
    expect(html).not.toMatch(/aviso-resolver-activo/);
    expect(html).toMatch(/aviso-atender v2-btn-ink/);
  });

  it('abierto: «Resuelto» se ve apretado y «Tomar» pasa a segundo plano', () => {
    const html = dibuja({ cerrando: true });
    expect(html).toMatch(/aviso-resolver-activo/);
    expect(html).toMatch(/aria-expanded="true"/);
    expect(html).not.toMatch(/v2-btn-ink/);
  });
});
