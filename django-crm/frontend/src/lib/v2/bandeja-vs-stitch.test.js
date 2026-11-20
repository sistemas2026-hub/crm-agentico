import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

/**
 * LA RÉPLICA, FIJADA CONTRA LA REFERENCIA.
 *
 * Hasta el 01/11/2026 la referencia era la pantalla de Stitch «Centro del
 * Supervisor NOC IA - Pendientes por Revisión» (proyecto 12743695992710804066,
 * pantalla 01f56da1b9f74b93b97b4ae841f2d830): una tabla de diez columnas.
 *
 * Desde el 01/11/2026 la referencia es el diseño que el usuario aprobó (la
 * segunda propuesta de la IA de diseño, portada en «El Supervisor NOC queda
 * como el diseño aprobado»): la bandeja deja de ser tabla y pasa a filas
 * compactas, agrupadas por plazo, sin fila de encabezados. Lo que esta guarda
 * afirma es la estructura de ESE diseño.
 *
 * Un cambio a propósito respecto de la referencia anterior: el tipo de
 * hallazgo vuelve a la fila, como una etiqueta corta. Stitch lo dejaba en el
 * detalle porque como columna de texto llenaba 121 filas con lo mismo; el
 * diseño aprobado lo muestra como etiqueta y la consulta de contenedor lo
 * oculta primero cuando falta ancho.
 *
 * POR QUÉ HACE FALTA
 * ------------------
 * La referencia vive fuera del repo. Nadie que toque esta bandeja dentro de
 * seis meses va a poder abrirla para comprobar si sigue pareciéndose, y una
 * celda de más o un rótulo cambiado no rompe nada: la pantalla sigue
 * funcionando, solo deja de ser el diseño que alguien aprobó. Esto lo
 * convierte en un fallo visible.
 *
 * LO QUE NO HACE
 * --------------
 * No compara píxeles ni estilos: eso necesita un navegador. Afirma la
 * ESTRUCTURA que la referencia fija -- qué celdas tiene cada fila, en qué
 * orden, y qué controles tiene la barra de filtros.
 *
 * Si el diseño cambia a propósito, esta prueba se actualiza con él. Que haya
 * que tocarla es el punto: obliga a decir que la réplica ya no es la de
 * antes, en vez de que se note meses después.
 */

const PAGINA = new URL(
  '../../routes/(app)/supervisor-noc/+page.svelte',
  import.meta.url
).pathname.replace(/^\/([A-Za-z]:)/, '$1');

/** Las celdas de cada fila del diseño aprobado, en su orden. */
const CELDAS = ['check', 'plazo', 'quien', 'prio', 'tipo', 'propone', 'tecnico', 'ids', 'accion'];

const fuente = () => readFileSync(PAGINA, 'utf8');

/** Las celdas `snv-c-*` del snippet `fila`, en orden. */
function celdasDeLaFila(html) {
  const inicio = html.indexOf('{#snippet fila(');
  if (inicio < 0) return [];
  const fin = html.indexOf('{/snippet}', inicio);
  return [...html.slice(inicio, fin).matchAll(/class="snv-c-([a-z]+)/g)].map((m) => m[1]);
}

describe('la bandeja replica el diseño aprobado', () => {
  it('cada fila tiene las nueve celdas, en el orden del diseño', () => {
    expect(celdasDeLaFila(fuente())).toEqual(CELDAS);
  });

  it('la bandeja se agrupa por plazo, no es una tabla', () => {
    const html = fuente();
    expect(html).toContain('agruparPorPlazo(');
    expect(html).not.toContain('snoc-tabla-bandeja');
  });

  it('la barra de filtros lleva los controles del diseño', () => {
    const html = fuente();
    for (const etiqueta of [
      'Pendientes',
      'Ya decididas',
      'Todas',
      'Con acción recomendada',
      'Sin acción recomendada',
      'Ordenar: Plazo',
      'Ordenar: Prioridad',
      'Limpiar filtros'
    ]) {
      expect(html).toContain(etiqueta);
    }
  });

  it('el KPI dice «SLA en riesgo», como la referencia', () => {
    // El texto del pedido decía «a riesgo» y la pantalla de Stitch dice «en
    // riesgo». Manda la referencia, y queda escrito para que no se cambie
    // otra vez leyendo el pedido en vez de la pantalla.
    const mod = readFileSync(
      new URL('./supervisor-noc-tablero.js', import.meta.url).pathname.replace(
        /^\/([A-Za-z]:)/,
        '$1'
      ),
      'utf8'
    );
    expect(mod).toContain("titulo: 'SLA en riesgo'");
    expect(mod).not.toContain("titulo: 'SLA a riesgo'");
  });

  it('la paginación dice cuántos registros hay, no solo las páginas', () => {
    expect(fuente()).toContain('Mostrando');
  });

  it('el reconocedor de celdas funciona', () => {
    // La comprobación se comprueba: un extractor que devolviera [] siempre
    // dejaría la primera prueba en rojo por la razón equivocada, y uno que
    // leyera fuera del snippet contaría celdas de otra parte de la pantalla.
    expect(
      celdasDeLaFila('{#snippet fila(p)}<div class="snv-c-uno"></div><div class="snv-c-dos"></div>{/snippet}<div class="snv-c-fuera">')
    ).toEqual(['uno', 'dos']);
    expect(celdasDeLaFila('<div class="snv-c-suelta"></div>')).toEqual([]);
  });
});
