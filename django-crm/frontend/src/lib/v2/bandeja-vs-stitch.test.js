import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

/**
 * LA RÉPLICA, FIJADA CONTRA LA REFERENCIA.
 *
 * La pantalla se ajustó a un diseño concreto: «Centro del Supervisor NOC IA -
 * Pendientes por Revisión», del proyecto de Stitch 12743695992710804066,
 * pantalla 01f56da1b9f74b93b97b4ae841f2d830. Lo que esta guarda afirma se
 * midió sobre el HTML de ESA pantalla, no sobre un recuerdo de ella.
 *
 * POR QUÉ HACE FALTA
 * ------------------
 * La referencia vive fuera del repo, detrás de una API con clave. Nadie que
 * toque esta tabla dentro de seis meses va a poder abrirla para comprobar si
 * sigue pareciéndose, y una columna de más o un rótulo cambiado no rompe
 * nada: la pantalla sigue funcionando, solo deja de ser la réplica que
 * alguien pidió. Esto lo convierte en un fallo visible.
 *
 * LO QUE NO HACE
 * --------------
 * No compara píxeles ni estilos: eso necesita un navegador. Afirma la
 * ESTRUCTURA que la referencia fija -- qué columnas, en qué orden, y qué
 * pastillas tiene la barra de filtros -- que es lo que de verdad se pidió
 * replicar y lo que más fácil se desvía.
 *
 * Si el diseño cambia a propósito, esta prueba se actualiza con él. Que haya
 * que tocarla es el punto: obliga a decir que la réplica ya no es la de
 * antes, en vez de que se note meses después.
 */

const PAGINA = new URL(
  '../../routes/(app)/supervisor-noc/+page.svelte',
  import.meta.url
).pathname.replace(/^\/([A-Za-z]:)/, '$1');

/** Las diez columnas de la referencia, en su orden. */
const COLUMNAS = [
  'N.º',
  'Prioridad',
  'Cliente',
  'Caso / OT',
  'Asunto del ticket',
  'Técnico actual',
  'SLA',
  'Antigüedad',
  'Propuesta',
  'Acción'
];

const fuente = () => readFileSync(PAGINA, 'utf8');

/** Los `<th>` de la tabla de la bandeja, en orden. */
function columnasDeLaTabla(html) {
  const tabla = html.indexOf('snoc-tabla-bandeja');
  if (tabla < 0) return [];
  const cuerpo = html.indexOf('</thead>', tabla);
  return [...html.slice(tabla, cuerpo).matchAll(/<th[^>]*>([^<]*)</g)]
    .map((m) => m[1].trim())
    .filter(Boolean);
}

describe('la bandeja replica la referencia de Stitch', () => {
  it('tiene las diez columnas, en el orden de la referencia', () => {
    expect(columnasDeLaTabla(fuente())).toEqual(COLUMNAS);
  });

  it('NO trae «Tipo de hallazgo» como columna', () => {
    // La referencia lo deja fuera de la tabla a propósito: vive en el
    // detalle. Como columna volvía a llenar 121 filas con el mismo texto.
    expect(columnasDeLaTabla(fuente())).not.toContain('Tipo de hallazgo');
  });

  it('la barra de filtros lleva las pastillas de la referencia', () => {
    const html = fuente();
    for (const etiqueta of [
      'Pendientes',
      'Ya decididas',
      'Todas',
      'Con propuesta',
      'Sin propuesta',
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

  it('el reconocedor de columnas funciona', () => {
    // La comprobación se comprueba: un extractor que devolviera [] siempre
    // dejaría las tres primeras pruebas en verde sin mirar nada.
    expect(columnasDeLaTabla('<table class="snoc-tabla-bandeja"><thead><tr><th>Uno</th><th>Dos</th></tr></thead>')).toEqual([
      'Uno',
      'Dos'
    ]);
    expect(columnasDeLaTabla('<table><thead><tr><th>Otra</th></tr></thead>')).toEqual([]);
  });
});
