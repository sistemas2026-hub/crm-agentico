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
      'Empresa',
      'Asistente',
      'Etiquetas y plantillas',
      'Avanzado (tickets del CRM)'
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

  /*
   * 12/11/2026 (auditoría del menú, §2 Administrar). Las siete subpáginas que
   * el motor no lee van juntas, AL FINAL y dicho; las tres que no enlazaba
   * nada aparecen; los tres pares con el mismo nombre dejan de llamarse igual.
   */
  it('las siete que el motor no lee van en «Avanzado», después de todo lo demás', () => {
    const html = dibujar(pendiente());
    const avanzado = html.indexOf('Avanzado (tickets del CRM)');
    expect(html).toContain('No cambian cómo atiende Dexter');
    for (const h of ['routing', 'escalation', 'ticket-approvals', 'reopen', 'inbound-email', 'macros', 'custom-fields']) {
      const i = html.indexOf(`href="/settings/${h}"`);
      expect(i, h).toBeGreaterThan(avanzado);
    }
    //  Y ninguna de Dexter quedó debajo.
    for (const h of ['/settings/bandeja', '/settings/variables', '/settings/canales/whatsapp']) {
      expect(html.indexOf(`href="${h}"`), h).toBeLessThan(avanzado);
    }
  });

  it('enlaza Instalaciones, Variables, Módulos y el Traspaso', () => {
    const html = dibujar(pendiente());
    for (const h of ['/settings/instalaciones', '/settings/variables', '/settings/modulos',
      '/settings/canales/whatsapp/traspaso']) {
      expect(html).toContain(`href="${h}"`);
    }
  });

  it('los pares ambiguos tienen nombres distintos', () => {
    const html = dibujar(pendiente());
    for (const t of ['Datos de facturación', 'Oficina virtual', 'Escalamiento de tickets (CRM)',
      'Traspaso a una persona', 'Macros (tickets)', 'Respuestas rápidas (Bandeja)']) {
      expect(html).toContain(t);
    }
    expect(html).not.toContain('<b>Organización</b>');
    expect(html).not.toContain('<b>Escalamiento</b>');
    expect(html).not.toContain('<b>Macros</b>');
  });

  it('Pagos y Variables dicen su estado real con la lectura que llega del motor', () => {
    const html = dibujar({
      ...pendiente(),
      motor: { pagos: { link: true, medios: 2 }, variables: { cantidad: 5, faltan: 1 } }
    });
    expect(html).toContain('Link cargado · 2 otros medios');
    expect(html).toContain('1 sin cargar');
    const sinLink = dibujar({ ...pendiente(), motor: { pagos: { link: false, medios: 0 }, variables: { cantidad: 3, faltan: 0 } } });
    expect(sinLink).toContain('Sin link de pago');
    expect(sinLink).toContain('3 cargadas');
  });
});
