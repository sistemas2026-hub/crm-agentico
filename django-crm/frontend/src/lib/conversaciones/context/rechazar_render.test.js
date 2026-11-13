/**
 * «Rechazar» en el panel de acciones (12/11/2026, auditoría del menú §4 ítem 2).
 *
 * Se afirma sobre lo que SALE dibujado: el botón aparece junto a «Aprobar» en
 * una pendiente, también en una vencida (rechazarla sigue siendo una decisión
 * que cuenta), y nunca en una que ya salió. Y la página lo cablea contra el
 * proxy de rechazo, no contra el de aprobar.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { render } from 'svelte/server';
import ActionsPanel from './ActionsPanel.svelte';

const texto = (/** @type {any} */ props) =>
  render(ActionsPanel, { props }).body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

const accion = (/** @type {any} */ extra) => ({
  id: 'a1', herramienta: 'crear_ticket', resumen: 'Crear ticket', estado: 'pendiente', expirada: false, ...extra
});
const manejadores = { onAprobar: () => {}, onRechazar: async () => '' };

describe('el botón de rechazar', () => {
  it('una pendiente ofrece aprobar Y rechazar', () => {
    const t = texto({ acciones: [accion()], ...manejadores });
    expect(t).toMatch(/Aprobar y ejecutar/);
    expect(t).toMatch(/Rechazar/);
  });

  it('una pendiente vencida no ofrece aprobar, pero sí rechazar', () => {
    const t = texto({ acciones: [accion({ expirada: true })], ...manejadores });
    expect(t).not.toMatch(/Aprobar y ejecutar/);
    expect(t).toMatch(/Rechazar/);
  });

  it('ninguna que ya salió lo ofrece', () => {
    for (const estado of ['ejecutando', 'ejecutada_ok', 'desconocida', 'rechazada']) {
      expect(texto({ acciones: [accion({ estado })], ...manejadores })).not.toMatch(/Rechazar/);
    }
  });

  it('sin manejador no se dibuja: un botón que no hace nada enseña a desconfiar', () => {
    expect(texto({ acciones: [accion()], onAprobar: () => {} })).not.toMatch(/Rechazar/);
  });
});

describe('la página lo cablea al proxy de rechazo', () => {
  const pagina = readFileSync(new URL('../../../routes/(app)/conversaciones/[id]/+page.svelte', import.meta.url), 'utf-8');
  it('manda el motivo a /rechazar y relee las acciones', () => {
    const cuerpo = pagina.slice(pagina.indexOf('async function rechazarAccion'));
    expect(cuerpo.slice(0, 1600)).toMatch(/\/acciones\/\$\{id\}\/rechazar/);
    expect(cuerpo.slice(0, 1600)).toMatch(/JSON\.stringify\(\{ motivo \}\)/);
    expect(cuerpo.slice(0, 1600)).toMatch(/acciones = \(await r\.json\(\)\)\.acciones/);
    expect(pagina).toMatch(/onRechazar=\{rechazarAccion\}/);
  });
});
