import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/**
 * LAS TARJETAS DE CUADRILLA NO REPARTEN SU CONTENIDO (28/10/2026).
 *
 * `.snoc-tarjeta` trae `justify-content: space-between`. En la rejilla de
 * cuadrillas la tarjeta se estira a la altura de la más larga, y con eso las
 * órdenes de una cuadrilla con pocas quedaban separadas por huecos enormes
 * (captura del usuario en Programación; Simular el día tenía lo mismo).
 */
const RUTA = 'src/routes/(app)/supervisor-noc';

describe('las tarjetas de cuadrilla', () => {
  for (const archivo of ['programacion/+page.svelte', 'despacho/+page.svelte']) {
    it(`${archivo}: el contenido va arriba`, () => {
      const fuente = readFileSync(`${RUTA}/${archivo}`, 'utf8');
      //  `pg-ct` desde el 07/11/2026: la tarjeta de Programación aprieta sus
      //  espacios con una clase propia en vez de `snoc-pila-xs`.
      const tarjetas = fuente.match(/<div class="snoc-tarjeta (?:snoc-pila-xs|pg-ct)" style="[^"]*"/g) ?? [];
      const deCuadrilla = tarjetas.filter((t) => t.includes('min-width:0'));

      expect(deCuadrilla.length).toBe(1);
      expect(deCuadrilla[0]).toContain('justify-content:flex-start');
    });
  }
});

/**
 * LO QUE EL CUADRO DE SEGUIMIENTO YA DICE NO SE REPITE EN LA TARJETA
 * (07/11/2026). El usuario, con la captura: «qué otro arreglo se puede hacer
 * para que no se vea tan maluco».
 *
 * Programación dibuja DOS cosas por cuadrilla: arriba el cuadro de
 * «Seguimiento de las cuadrillas» —estado y OT como título, los minutos en
 * grande, «3 de 6 · salió 07:42» con barra— y abajo su tarjeta de lo
 * publicado. La tarjeta repetía el día en una línea gris chica
 * («Todavía no sale · 0 de 10 hechas»), cuatro veces, debajo de un cuadro que
 * lo decía mejor.
 *
 * Se afirma sobre el DATO (`resumen_del_dia`) y no sobre el nombre de la
 * función que lo escribía: volver a imprimirlo de cualquier otra forma
 * también tiene que leer ese campo, así que la mutación no se escapa
 * renombrando. Y se exige que el cuadro siga estando: sin él, no habría nada
 * que repita y la tarjeta tendría que volver a decirlo.
 */
describe('el día de la cuadrilla, una sola vez en la pantalla', () => {
  const fuente = () => readFileSync(`${RUTA}/programacion/+page.svelte`, 'utf8');

  it('el cuadro de seguimiento se dibuja', () => {
    expect(fuente()).toContain('<SeguimientoDeCuadrillas');
  });

  //  EL CABLEADO (07/11/2026, segunda vuelta). `MaterialDeLaCuadrilla` solo
  //  puede callar lo repetido si alguien le dice QUÉ le falta a todas, y eso
  //  lo calcula la página. La decisión y su efecto se miden en las pruebas de
  //  `material-del-dia` y del componente; lo que esta guarda cubre es el
  //  cable: sin él, el componente recibe una lista vacía y vuelve el muro.
  //  Es una afirmación sobre el archivo y no sobre lo dibujado, porque la
  //  ruta no se renderiza en ninguna prueba (arnés solo-SSR).
  it('la página calcula lo que le falta a todas y se lo pasa al material', () => {
    const f = fuente();
    expect(f).toContain('equiposDeTodas(material?.cuadrillas ?? [])');
    expect(f).toMatch(/<MaterialDeLaCuadrilla[^/>]*\{comunes\}/);
  });

  //  Lo mismo para el bloque «Para que el día salga completo» (07/11/2026,
  //  tercera vuelta): sin el cable, el bloque pierde el renglón de las apps
  //  y esa frase se cae de la pantalla, porque ya no está el párrafo suelto
  //  que la decía antes.
  it('y le pasa al bloque las apps que no bajaron lo publicado', () => {
    const f = fuente();
    expect(f).toMatch(/<FaltantesDelDia[\s\S]*?apps=\{resumenDeLoSinBajar\(publicado\.cuadrillas\)\}/);
    //  Y ya no queda el párrafo rojo suelto que repetía esa misma frase.
    expect(f).not.toContain('snoc-error-txt">{resumenDeLoSinBajar');
  });

  it('y la tarjeta de lo publicado no vuelve a leer el resumen del día', () => {
    //  Sin comentarios: el porqué de la decisión los nombra a propósito.
    const sinComentarios = fuente().replace(/<!--[\s\S]*?-->/g, '');
    expect(sinComentarios).not.toContain('resumen_del_dia');
  });
});
