import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import MaterialDeLaCuadrilla from './MaterialDeLaCuadrilla.svelte';

/**
 * El material de una cuadrilla en Programación (29/10/2026). El usuario, con la
 * tarjeta a la vista: «arriba se ve muy feo… el acta está de más… y los avisos,
 * que se contraigan como el material». Se mide lo que se dibuja, con la forma
 * de `campo/material_del_dia.py`.
 */
const FALTA = 'Le falta material para completar el kit (13 de 14 materiales): sale con lo que hay en bodega.';
const CATV = 'Sale sin ONU CATV: no puede hacer el trabajo que lo necesita.';
const WIFI = 'Sale sin ONU WIFI: no puede hacer el trabajo que lo necesita.';

const m = {
  kit: 'Kit de instalacion',
  kit_por: 'se parece por el nombre a «Instalacion»',
  bodega: 'BOG-SOLEDAD',
  bodega_por: 'su zona la nombra',
  lider: 'JEIDER AMELL',
  acta: 'MAT-20261029-f7fa6fcc',
  cargado_en: '2026-10-29T12:36:00-05:00',
  avisos: [FALTA, CATV, WIFI],
  lineas: [
    { material: 'CABLE DROP', unidad: 'm', kit: '150', en_mano: '0', necesita: '150', asignado: '0', falta: '150' }
  ]
};

const html = (props) => render(MaterialDeLaCuadrilla, { props }).body;

/**
 * EL TEXTO QUE SE LEE, sin etiquetas ni los marcadores que mete Svelte. Un
 * `toContain` sobre el HTML crudo no puede afirmar sobre una frase que cruza
 * de una etiqueta a la otra, que es justo donde se perdia el espacio.
 * @param {string} h
 */
const leido = (h) => h.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]+>/g, '');

describe('el material de una cuadrilla', () => {
  it('a la vista: el kit, de dónde, para quién y cuándo se cargó; sin el acta', () => {
    const h = html({ m });
    //  LA FRASE COMO SE LEE, no un pedazo que empieza DESPUES del defecto
    //  (07/11/2026). Esta prueba afirmaba «de BOG-SOLEDAD para JEIDER AMELL»
    //  por separado, y por eso estuvo en verde mientras la pantalla decia
    //  «Kit de instalacionde BOG-SOLEDAD».
    //
    //  Svelte RECORTA el espacio con el que arranca el contenido de un
    //  elemento --medido el 07/11/2026 compilando la misma linea para cliente
    //  y para servidor: los dos se lo comen-- y el corte caia justo entre las
    //  dos etiquetas, donde un `toContain` sobre el HTML crudo no mira.
    expect(leido(h)).toContain('Kit de instalacion de BOG-SOLEDAD para JEIDER AMELL');
    expect(h).toContain('Cargado a las 12:36');
    expect(h).not.toContain('MAT-20261029');
  });

  //  EL MURO (07/11/2026). El usuario, con la captura de cuatro tarjetas:
  //  «qué otro arreglo se puede hacer para que no se vea tan maluco». La
  //  línea decía «Falta material · sale sin ONU CATV y ONU WIFI» en rojo y en
  //  negrita, idéntica en las cuatro. «Falta material» ya lo dicen las
  //  pastillas de arriba: repetirlo gasta la única línea que tenía algo
  //  propio que decir.
  it('EL DEFECTO: la pastilla no repite lo que ya dicen las cuentas de arriba', () => {
    const h = html({ m });
    const antesDeAbrir = h.slice(0, h.indexOf('</summary>'));
    expect(antesDeAbrir).not.toContain('Falta material');
    expect(antesDeAbrir).toContain('Sin ONU CATV y ONU WIFI');
  });

  it('y el texto entero no se pierde: sigue adentro del desplegable', () => {
    const h = html({ m });
    expect(h).toMatch(/<details class="mc-avisos/);
    expect(h).toContain(CATV);
    expect(h).toContain(FALTA);
  });

  it('un solo aviso también va en pastilla: una frase larga por tarjeta es el mismo muro', () => {
    //  Reemplaza la regla del 29/10 de mostrarlo entero. Con una tarjeta por
    //  cuadrilla, cuatro frases largas iguales pesan lo mismo tenga la
    //  cuadrilla un aviso o tres.
    const h = html({ m: { ...m, avisos: [CATV] } });
    expect(h.slice(0, h.indexOf('</summary>'))).toContain('Sin ONU CATV');
    expect(h).not.toContain('class="mc-aviso ');
    expect(h).toContain(CATV);
  });

  it('sin equipo nombrado la pastilla dice que falta material, que es lo que hay', () => {
    const h = html({ m: { ...m, avisos: [FALTA] } });
    expect(h.slice(0, h.indexOf('</summary>'))).toContain('Falta material');
  });

  it('sin avisos no dibuja pastilla', () => {
    expect(html({ m: { ...m, avisos: [] } })).not.toContain('mc-chip');
  });

  it('el porqué del kit y de la bodega va adentro de la lista, no a la vista', () => {
    const h = html({ m });
    const lineas = h.slice(h.indexOf('mc-lineas'));
    expect(lineas).toContain('Kit: lo eligió el Supervisor: se parece por el nombre');
    expect(lineas).toContain('Bodega: lo eligió el Supervisor: su zona la nombra');
    expect(h.slice(0, h.indexOf('mc-lineas'))).not.toContain('lo eligió el Supervisor');
  });

  it('con labor de apoyo dice los dos kits (30/10/2026)', () => {
    const h = html({ m: { ...m, kit: 'Kit de soporte', kit_apoyo: 'Kit de instalacion' } });
    expect(h).toMatch(/Kit de soporte<\/strong>(?:<!--[^>]*-->)?<span[^>]*>\s*\+\s*<\/span><strong[^>]*>Kit de instalacion<\/strong>/);
    expect(html({ m })).not.toContain(' + ');
  });

  it('sin cargar dice que es una propuesta', () => {
    expect(html({ m: { ...m, cargado_en: null } })).toContain('Propuesta');
  });
});
