/**
 * Que ninguna clase del elemento RAÍZ de un componente se repita en un
 * descendiente suyo.
 *
 * POR QUÉ EXISTE ESTE ARCHIVO
 * ---------------------------
 * El 21/09/2026, en el primer QA visual real de la Bandeja, la fila abierta de
 * la cola se veía verde oliva, más chica, con un punto inyectado adelante, sin
 * llenar la columna y desbordándola 147px (con barra de scroll horizontal).
 *
 * La causa era `.activa`, usada para dos cosas dentro del MISMO componente:
 *
 *     <a class="fila" class:activa={...}>   la conversación abierta
 *       ...
 *       <span class="activa">Activa</span>  el punto de "se movió recién"
 *
 * El scope de Svelte no las separa: las dos viven en el mismo archivo, así que
 * las dos reciben el mismo sufijo. `.fila.activa` y `.activa` quedan con la
 * misma especificidad (0,2,0) y gana la última del archivo -- que era la del
 * punto. El `<a>` heredaba `display: inline-flex`, `color: moss`,
 * `font-size: 10.5px` y un `::before` de 6px.
 *
 * POR QUÉ NO ALCANZABA CON MIRARLO
 * --------------------------------
 * El propio componente TENÍA el comentario advirtiendo de la colisión, y decía
 * que el scope las mantenía separadas. Estaba equivocado, y estuvo equivocado
 * hasta que alguien abrió la pantalla. Un comentario no es una guarda.
 *
 * QUÉ AFIRMA, Y QUÉ NO
 * --------------------
 * NO afirma que la clase se llame `.latido` hoy: eso sería atarse al arreglo en
 * vez de al defecto, y un renombre legítimo lo pondría rojo sin motivo. Afirma
 * la CONDICIÓN que hace posible el defecto -- que la raíz y un descendiente
 * compartan nombre de clase --, así que sigue sirviendo con cualquier nombre
 * futuro y cubre también a `.fila`, `.pide` y a las que se agreguen.
 *
 * Es un test de texto porque vitest corre en `node` sin el plugin de Svelte y
 * no puede compilar un `.svelte` (mismo motivo que `t6_cableado.test.js`). Lo
 * que se mide acá no es una cadena elegida a dedo: es la intersección de dos
 * conjuntos leídos del marcado.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const leer = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf-8');

/** El marcado: entre el `</script>` y el `<style>`. */
function marcado(fuente) {
  const desde = fuente.indexOf('</script>');
  const hasta = fuente.lastIndexOf('<style');
  return fuente.slice(desde === -1 ? 0 : desde + 9, hasta === -1 ? undefined : hasta);
}

/**
 * Las clases del PRIMER elemento del marcado --la raíz del componente-- y las
 * de todo lo que viene después.
 *
 * Toma tanto `class="a b"` como la directiva `class:x={...}` de Svelte, que es
 * justo por donde entró el defecto: `.activa` llegaba al `<a>` por directiva y
 * al `<span>` por atributo, así que buscar sólo `class="` no lo veía.
 */
function clasesDeRaizYDescendientes(fuente) {
  const html = marcado(fuente);
  const raizAbre = html.indexOf('<');
  // El final de la etiqueta de apertura de la raíz: el primer '>' que no esté
  // dentro de unas llaves de Svelte ni de unas comillas.
  let i = raizAbre;
  let comilla = null;
  let llaves = 0;
  for (; i < html.length; i++) {
    const c = html[i];
    if (comilla) {
      if (c === comilla) comilla = null;
      continue;
    }
    if (c === '"' || c === "'") comilla = c;
    else if (c === '{') llaves++;
    else if (c === '}') llaves--;
    else if (c === '>' && llaves === 0) break;
  }
  const etiquetaRaiz = html.slice(raizAbre, i + 1);
  const resto = html.slice(i + 1);

  const clasesDe = (trozo) => {
    const nombres = new Set();
    for (const m of trozo.matchAll(/class="([^"{}]*)"/g)) {
      for (const n of m[1].split(/\s+/)) if (n) nombres.add(n);
    }
    for (const m of trozo.matchAll(/\bclass:([A-Za-z0-9_-]+)/g)) nombres.add(m[1]);
    return nombres;
  };

  return { raiz: clasesDe(etiquetaRaiz), descendientes: clasesDe(resto) };
}

/* Los componentes de la cola cuya raíz lleva clases con estado. Si mañana se
   agrega otro, se suma acá: el costo es una línea y el defecto que evita no se
   ve leyendo el archivo. */
const COMPONENTES = [
  ['ConversationRow.svelte', './ConversationRow.svelte'],
  ['ConversationList.svelte', './ConversationList.svelte'],
  ['QueueFilters.svelte', './QueueFilters.svelte'],
  ['QueueTabs.svelte', './QueueTabs.svelte']
];

describe('ninguna clase de la raíz se repite adentro', () => {
  for (const [nombre, ruta] of COMPONENTES) {
    it(`${nombre}: raíz y descendientes no comparten nombre de clase`, () => {
      const { raiz, descendientes } = clasesDeRaizYDescendientes(leer(ruta));
      const chocan = [...raiz].filter((c) => descendientes.has(c));
      expect(chocan).toEqual([]);
    });
  }
});

describe('la lectura del marcado mide lo que dice medir', () => {
  // Controles positivos. Sin esto, un parseo que devolviera conjuntos vacíos
  // dejaría los cuatro casos de arriba en verde para siempre -- que es
  // exactamente la forma en que una guarda deja de guardar sin avisar.
  it('encuentra las clases de la raíz, incluidas las de directiva', () => {
    const { raiz } = clasesDeRaizYDescendientes(leer('./ConversationRow.svelte'));
    expect(raiz.has('fila')).toBe(true);
    expect(raiz.has('pide')).toBe(true);
    expect(raiz.has('activa')).toBe(true);
  });

  it('encuentra las clases de adentro', () => {
    const { descendientes } = clasesDeRaizYDescendientes(leer('./ConversationRow.svelte'));
    expect(descendientes.has('cuerpo')).toBe(true);
    expect(descendientes.has('quien')).toBe(true);
  });

  it('y detecta la colisión cuando la hay', () => {
    // El defecto real del 21/09/2026, reconstruido. Si el parseo dejara de ver
    // las directivas o los descendientes, esto se pondría verde y avisaría.
    const roto = `</script>
      <a class="fila" class:activa={c.id === abierta}>
        <span class="activa">Activa</span>
      </a>
    <style></style>`;
    const { raiz, descendientes } = clasesDeRaizYDescendientes(roto);
    expect([...raiz].filter((c) => descendientes.has(c))).toEqual(['activa']);
  });
});
