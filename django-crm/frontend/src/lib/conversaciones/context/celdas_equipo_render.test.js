/**
 * Las celdas de la telemetría óptica, dibujadas de verdad (10/11/2026).
 *
 * Nace de una captura: «Temperatura», «Tx del equipo» y «RX en la OLT» con un
 * guion, que se lee como un dato que falta. Las tres salen de la lectura
 * profunda, que pide el botón; y «RX en la OLT» era el mismo número que
 * «Subida (1310 nm)» (medido el 19/10/2026: -20,87 en las dos).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { render } from 'svelte/server';
import NetworkPanel from './NetworkPanel.svelte';

const texto = (/** @type {any} */ props) =>
  render(NetworkPanel, { props }).body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

const optica = (/** @type {any} */ profundidad = null) => ({
  disponible: true, motivo: null, leido_en: new Date().toISOString(), umbral_rx_dbm: -27,
  optica: {
    serial: 'ABCD12345678',
    estado: { onu_status: 'Online', last_status_change: '2026-11-10 02:33:47' },
    senal: { onu_signal: 'Very good', onu_signal_1490: '-20.7', onu_signal_1310: '-27.45' },
    profundidad
  }
});

describe('las celdas del equipo', () => {
  it('lo que recibe la OLT es UNA celda, con el número de la lectura liviana', () => {
    const t = texto({ optica: optica(), conversacionId: 'c1' });
    expect(t).toMatch(/Lo que recibe la OLT del equipo \(1310 nm\) -27\.45 dBm/);
    expect(t).not.toMatch(/RX en la OLT/);
    expect(t).not.toMatch(/Subida \(1310 nm\)/);
  });

  it('sin la lectura profunda, temperatura y Tx dicen cómo se obtienen, no un guion', () => {
    const t = texto({ optica: optica(), conversacionId: 'c1' });
    expect(t).toMatch(/Temperatura Se lee con «Consultar ahora»/);
    expect(t).toMatch(/Tx del equipo Se lee con «Consultar ahora»/);
  });

  it('con la lectura profunda, muestran el valor', () => {
    const t = texto({ optica: optica({ temperatura: '35', tx: '2.31', olt_rx: '-27.45' }), conversacionId: 'c1' });
    expect(t).toMatch(/Temperatura 35 °C/);
    expect(t).toMatch(/Tx del equipo 2\.31 dBm/);
    expect(t).not.toMatch(/Se lee con «Consultar ahora»/);
  });
});

describe('la lectura profunda sola, solo con una persona en el caso', () => {
  const fuente = readFileSync(fileURLToPath(new URL('./NetworkPanel.svelte', import.meta.url)), 'utf-8');

  it('al abrir, la profunda depende de profundaSola y de que no esté ya leída', () => {
    const alAbrir = fuente.slice(fuente.indexOf('onMount(() => {'), fuente.indexOf('function leerProfundaSiFalta'));
    expect(alAbrir).toMatch(/if \(profundaSola\) \{\s*leerProfundaSiFalta\(\);/);
    const leer = fuente.slice(fuente.indexOf('function leerProfundaSiFalta'));
    expect(leer.slice(0, 120)).toMatch(/if \(profundo\) return;/);
  });

  it('la página la enciende solo con la conversación escalada y abierta', () => {
    const pagina = readFileSync(
      fileURLToPath(new URL('../../../routes/(app)/conversaciones/[id]/+page.svelte', import.meta.url)), 'utf-8');
    expect(pagina).toMatch(/profundaSola=\{!!conversacion\?\.escalada_a_humano && conversacion\.estado !== 'cerrada'\}/);
  });
});
