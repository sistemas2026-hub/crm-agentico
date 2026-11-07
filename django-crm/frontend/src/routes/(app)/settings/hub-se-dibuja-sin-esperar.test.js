/**
 * CONFIGURACION SE DIBUJA SIN ESPERAR A NADIE  --  01/11/2026
 * ==========================================================
 *
 * "La ventana configuracion demora para abrir o en ocasiones no abre." La
 * carga ya no espera ninguna lectura (settings-plazo.test.js): cada una llega
 * como promesa. Esta prueba renderiza la PAGINA de verdad y afirma las dos
 * mitades de ese contrato:
 *
 * - con todo pendiente, la pagina se dibuja entera -- encabezado, los cuatro
 *   grupos, cada destino -- sin valores y sin romperse por un dato que todavia
 *   no llego;
 * - con los datos ya resueltos, cada fila muestra su valor.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import Hub from './+page.svelte';

const nunca = () => new Promise(() => {});

/** Las claves que la carga devuelve como promesa (ver settings.js). */
const CLAVES = [
  'organizacion', 'calendar', 'tokenTotals', 'peopleTotals', 'routingTotals',
  'escalationTotals', 'mailboxTotals', 'reopen', 'approvalRules', 'approvalTotals',
  'macroTotals', 'tagTotals', 'fieldTotals', 'avisosCampo', 'motor'
];

const pendiente = () =>
  Object.fromEntries([['orgNombre', 'Rapilink'], ...CLAVES.map((c) => [c, nunca()])]);

const dibujar = (data) => render(Hub, { props: { data } }).body;

describe('el hub de Configuracion', () => {
  it('EL EFECTO: con todas las lecturas pendientes, se dibuja entero', () => {
    const html = dibujar(pendiente());
    expect(html).toContain('Configuración');
    expect(html).toContain('Rapilink');
    for (const grupo of [
      'Personas y acceso',
      'Cómo se gestionan los tickets',
      'Asistente',
      'Palabras y campos compartidos'
    ]) {
      expect(html).toContain(grupo);
    }
    for (const destino of ['/team', '/settings/escalation', '/settings/business-hours', '/settings/macros', '/settings/pagos']) {
      expect(html).toContain(`href="${destino}"`);
    }
    //  Ninguna fila inventa un valor que no llego.
    expect(html).not.toContain('prioridades');
    expect(html).not.toContain('undefined');
  });

  it('con los datos resueltos, cada fila trae su valor', () => {
    const html = dibujar({
      ...pendiente(),
      organizacion: { name: 'Rapilink', company_name: 'Rapilink SAS', member_count: 12 },
      calendar: { name: 'Oficina', days: [{ open: '08:00', close: '17:00' }] },
      escalationTotals: { active: 2, count: 4, breaches_unhandled_30d: 0 },
      macroTotals: { org: 3, with_unknown_placeholders: 0 },
      approvalRules: [],
      approvalTotals: { active: 1 }
    });
    expect(html).toContain('2 de 4 prioridades');
    expect(html).toContain('Oficina · 1 días, 08:00-17:00');
    expect(html).toContain('3 compartidas');
    expect(html).toContain('Rapilink SAS');
    expect(html).toContain('12');
  });
});
