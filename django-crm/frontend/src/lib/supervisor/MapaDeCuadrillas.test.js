import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { render } from 'svelte/server';

import MapaDeCuadrillas from './MapaDeCuadrillas.svelte';
import { seDibujaElMapa } from './dia-publicado.js';
import { opcionesDelIcono, tecnicoDePie } from './icono-de-cuadrilla.js';

/**
 * EL MAPA DE CUADRILLAS (31/10/2026).
 *
 * Se mide lo que se dibuja en el servidor: la cabecera, la cuenta de quién
 * reporta, la advertencia de lo que un punto significa y quién quedó sin
 * señal. Leaflet solo corre en el navegador (`onMount`), así que los pines no
 * entran acá — por eso lo que se afirma es lo que el supervisor LEE alrededor
 * del mapa, que es donde está el riesgo de que un punto se lea como un hecho
 * sobre una persona.
 */
const posicion = (extra = {}) => ({
  latitud: 10.9185, longitud: -74.7668, precision_m: 8, bateria: 72,
  minutos: 3, fresca: true, precision_pobre: false,
  medida_en: '2026-10-31T11:20:00-05:00', de: 'Mario Vásquez', ...extra
});
const cuadrilla = (extra = {}) => ({
  jornada: 'j-1', cuadrilla: 'Cuadrilla #5', ordenes: [], posicion: posicion(), ...extra
});
const html = (cuadrillas) => render(MapaDeCuadrillas, { props: { cuadrillas } }).body;

describe('el mapa de cuadrillas', () => {
  it('cuenta cuántas reportan, sobre el total', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null }),
      cuadrilla({ jornada: 'j-3', cuadrilla: 'Cuadrilla #1', posicion: null })
    ]);

    expect(h).toContain('1 de 3 reportando');
  });

  it('nombra a las que están sin señal, en vez de dejarlas invisibles', () => {
    const h = html([
      cuadrilla(),
      cuadrilla({ jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null })
    ]);

    expect(h).toContain('Sin señal:');
    expect(h).toContain('Cuadrilla #3');
    expect(h).not.toMatch(/Sin señal:[^<]*Cuadrilla #5/);
  });

  it('con todas reportando no dice que falte ninguna', () => {
    expect(html([cuadrilla()])).not.toContain('Sin señal:');
  });

  it('ninguna capa pide clave: CARTO sirve las imágenes tachadas', () => {
    //  EL DEFECTO DEL 05/11/2026: CARTO pasó a exigir clave y empezó a
    //  servir cada tile con «API KEY REQUIRED» encima. El mapa quedó
    //  ilegible y ninguna prueba lo vio, porque ninguna miraba de dónde
    //  salen las imágenes. Esri no pide clave --es el proveedor del
    //  satélite, que ya andaba--.
    const fuente = readFileSync(
      'src/lib/supervisor/MapaDeCuadrillas.svelte', 'utf8');
    const urls = fuente.match(/url: '([^']+)'/g) ?? [];

    expect(urls.length).toBe(2);
    for (const u of urls) {
      expect(u).not.toMatch(/cartocdn|mapbox|api[_-]?key|apikey|access_?token/i);
      expect(u).toContain('arcgisonline.com');
    }
  });

  it('ofrece Mapa y Satélite, y arranca en Mapa', () => {
    const h = html([cuadrilla()]);

    expect(h).toContain('>Mapa<');
    expect(h).toContain('>Satélite<');
    //  Y SE VE: un selector escondido pasa un `toContain` y no sirve a
    //  nadie. Se mira la etiqueta entera, no un patrón con el orden de los
    //  atributos adentro -- ese orden lo decide Svelte y ya me engañó una vez.
    const etiqueta = h.match(/<div[^>]*mp-capas[^>]*>/)?.[0] ?? '';
    expect(etiqueta).not.toBe('');
    expect(etiqueta).not.toContain('hidden');
    //  Svelte pone su sufijo PRIMERO: `class="svelte-… on"`.
    expect(h).toMatch(/class="[^"]*\bon"[^>]*>Mapa</);
    expect(h).not.toMatch(/class="[^"]*\bon"[^>]*>Satélite</);
  });

  it('dice siempre qué significa un punto y qué significa lo atenuado', () => {
    const h = html([cuadrilla()]);

    expect(h).toContain('no que la persona esté ahí');
    expect(h).toContain('es dónde estuvo, no dónde está');
  });

  it('sin ninguna cuadrilla DICE que no hay a quién ubicar, y dibuja la caja', () => {
    //  01/11/2026: el mapa vivía dentro del bloque de cuadrillas, así que un
    //  día sin cuadrillas armadas no lo dibujaba — y desde afuera eso no se
    //  distingue de un mapa roto. Ahora se ve siempre y dice por qué está
    //  vacío.
    for (const vacio of [[], undefined]) {
      const h = html(vacio);
      expect(h).toContain('0 de 0 reportando');
      expect(h).toContain('class="mp-caja');
      expect(h).toContain('No hay cuadrillas armadas para este día');
    }
  });

  it('con cuadrillas NO dice que no haya ninguna', () => {
    expect(html([cuadrilla()])).not.toContain('No hay cuadrillas armadas');
  });
});

describe('cuándo se dibuja el mapa', () => {
  it('solo si lo que se mira es hoy', () => {
    expect(seDibujaElMapa('2026-11-01', '2026-11-01')).toBe(true);
  });

  it('un día pasado NO lo dibuja: no hay posiciones de ese día', () => {
    expect(seDibujaElMapa('2026-10-25', '2026-11-01')).toBe(false);
  });

  it('un día futuro tampoco', () => {
    expect(seDibujaElMapa('2026-11-05', '2026-11-01')).toBe(false);
  });

  it('si la carga falló y los dos quedan vacíos, tampoco: no es que sea hoy', () => {
    //  Cuando el load no pudo leer, `dia` y `hoy` vienen los dos en ''. Sin
    //  la guarda, '' === '' daba true y el mapa se dibujaba sobre nada.
    expect(seDibujaElMapa('', '')).toBe(false);
    expect(seDibujaElMapa(null, null)).toBe(false);
  });

  it('sin saber cuál es hoy no se dibuja, en vez de adivinar', () => {
    //  EL DEFECTO DEL 01/11/2026: la pantalla comparaba contra una zona
    //  horaria escrita a mano y el mapa no aparecía nunca.
    for (const sinHoy of ['', null, undefined]) {
      expect(seDibujaElMapa('2026-11-01', sinHoy)).toBe(false);
    }
  });
});


describe('el técnico en el mapa', () => {
  it('el color dice lo mismo que decía el punto: lleno es de ahora', () => {
    const fresca = tecnicoDePie('#1f7a3d', true);
    const vieja = tecnicoDePie('#6b7280', false);

    //  TIÑE EL CHALECO ENTERO, su frente y su costado, no una franja suelta.
    expect(fresca.match(/#1f7a3d/g)?.length ?? 0).toBeGreaterThanOrEqual(2);
    expect(fresca).toContain('opacity:1');
    //  Lo viejo se ve viejo: es dónde estuvo, no dónde está.
    expect(vieja).toContain('opacity:0.5');
  });

  it('es un dibujo, no una imagen: nítido en cualquier zoom', () => {
    const svg = tecnicoDePie('#1f7a3d', true);
    expect(svg.startsWith('<svg')).toBe(true);
    expect(svg).toContain('viewBox="0 0 34 46"');
    expect(svg).not.toContain('<img');
    //  LO QUE LO HACE VISIBLE sobre el satélite, que es el motivo del
    //  cambio: el halo blanco que lo recorta y el casco, que no aparece en
    //  una foto aérea de un barrio.
    expect(svg).toContain('stroke="#fff"');
    expect(svg).toContain('#f2b705');
  });

  it('el punto cae en los pies, no en el centro del dibujo', () => {
    //  Si se ancla al medio, el vehículo queda corrido respecto de la calle
    //  y el supervisor lo lee como que está en otro lado.
    const o = opcionesDelIcono('#1f7a3d', true);
    expect(o.iconAnchor).toEqual([17, 42]);
    expect(o.iconSize).toEqual([34, 46]);
    expect(o.className).toBe('mp-vehiculo');
  });
});
