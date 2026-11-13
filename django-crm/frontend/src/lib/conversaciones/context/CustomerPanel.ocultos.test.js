/**
 * Un campo filtrado se dice «oculto», no se deja en blanco  (12/11/2026).
 *
 * El motor filtra la ficha según el área de quien mira
 * (nucleo/seguridad/ficha_por_area.py) y manda `_ocultos`. Si el panel
 * simplemente no dibujara el renglón, «Documento» desaparecería y se leería
 * como "este cliente no tiene cédula cargada" -- que es falso. Se afirma
 * sobre lo que SALE dibujado, en las dos direcciones.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import CustomerPanel from './CustomerPanel.svelte';

const texto = (/** @type {any} */ props) =>
  render(CustomerPanel, { props }).body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

const conversacion = { id: 'c1', estado: 'abierta', usuario_externo: '573001112233', id_cliente: '77' };

describe('la ficha según quién mira', () => {
  it('la cédula oculta dice «Oculto para tu área» y no muestra el número', () => {
    const t = texto({
      conversacion,
      ficha: { plan_internet: 'PLAN 300', estado: 'Activo', _ocultos: ['cedula', 'email', 'coordenadas'] }
    });
    expect(t).toMatch(/Documento\s+Oculto para tu área/);
    expect(t).toContain('PLAN 300');
  });

  it('una sección entera oculta igual se dibuja, con el aviso', () => {
    const t = texto({ conversacion, ficha: { plan_internet: 'PLAN 300', _ocultos: ['direccion', 'localidad', 'ciudad', 'zona'] } });
    expect(t).toContain('Ubicación');
    expect(t).toMatch(/Dirección\s+Oculto para tu área/);
  });

  it('quien sí la ve, ve el número y ningún «oculto»', () => {
    const t = texto({ conversacion, ficha: { cedula: '1234567890', direccion: 'CALLE 1', _ocultos: [] } });
    expect(t).toMatch(/Documento\s+1234567890/);
    expect(t).not.toContain('Oculto');
  });

  it('un campo que no vino y no está oculto sigue sin renglón (el cliente no lo tiene)', () => {
    const t = texto({ conversacion, ficha: { plan_internet: 'PLAN 300', _ocultos: [] } });
    expect(t).not.toContain('Documento');
    expect(t).not.toContain('Ubicación');
  });
});
