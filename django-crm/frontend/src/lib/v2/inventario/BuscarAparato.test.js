import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'svelte/server';

/*
 * La historia de un aparato enlaza la orden en la que se movió (12/11/2026).
 * El backend mandaba `orden` (`campo/services/inventario.py::historia_de`) y la
 * pantalla lo descartaba. Se recorre el salto de la web con la forma del
 * backend: el servidor pasa la historia entera y la pantalla la dibuja.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { leerSerie } = await import('$lib/server/v2/inventario.js');
const { default: BuscarAparato } = await import('./BuscarAparato.svelte');

const ORDEN = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const APARATO = {
  serie: 'ZTEG123', material: { codigo: 'ONT', nombre: 'ONT ZTE' },
  donde_esta: null, cuadra_con_el_libro: true,
  historia: [
    { en: '2026-11-10T14:00:00-05:00', tipo: 'despacho', estado: 'aceptado',
      desde: 'Bodega', hacia: 'Carlos', orden: null, orden_numero: null, motivo: '' },
    { en: '2026-11-11T10:00:00-05:00', tipo: 'consumo', estado: 'aceptado',
      desde: 'Carlos', hacia: null, orden: ORDEN, orden_numero: 188, motivo: '' }
  ]
};

beforeEach(() => {
  apiRequest.mockReset();
});

describe('la historia de un aparato', () => {
  it('el movimiento con orden enlaza a su página como OT-n', async () => {
    apiRequest.mockResolvedValue({ activos: [APARATO] });
    const consulta = await leerSerie({ cookies: {} }, 'ZTEG123');
    const b = render(BuscarAparato, { props: { consulta, serieConsultada: 'ZTEG123' } }).body;
    expect(b).toContain(`href="/ordenes/${ORDEN}"`);
    expect(b).toContain('OT-188');
    // Un movimiento sin orden no inventa un enlace.
    expect(b.match(/href="\/ordenes\//g)?.length).toBe(1);
  });
});
