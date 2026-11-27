import { describe, expect, it, vi } from 'vitest';
import { render } from 'svelte/server';

//  `enhance` es del navegador: en el dibujo del servidor no hace nada.
vi.mock('$app/forms', () => ({ enhance: () => ({ destroy() {} }) }));

const { default: Pagina } = await import('./+page.svelte');

/**
 * LAS TRABADAS SE VEN CON SUS BOTONES (27/11/2026), probado por lo que dibuja
 * la página. Un contrato SIN solicitud (sale del ticket, como la OT-502).
 */
/** @param {any} alta */
const pintar = (alta) => render(Pagina, {
  props: {
    data: /** @type {any} */ ({
      vista: 'por_activar', instalaciones: [], solicitudes: [], estado: '', automatica: false,
      sinPermiso: false, error: '',
      trabadas: [{ orden_id: 'o-2', numero: 502, cliente: 'CLIENTE DE PRUEBA',
                   contrato: { id: 'con-502', numero: 'C-2026-000502', alta } }]
    }),
    form: null
  }
}).body;

describe('Instalaciones → Por activar: las que no quedaron creadas', () => {
  it('POR REVISAR: dice qué pasa y ofrece «Sí quedó» y «No quedó creado»', () => {
    const html = pintar({ estado: 'por_revisar', por_revisar: true, se_puede_pedir: false,
                          detalle: 'Se pidió crear al cliente y no se pudo confirmar si quedó.' });
    expect(html).toContain('OT-502');
    expect(html).toContain('No se sabe si la instalación quedó creada');
    expect(html).toContain('No quedó creado');
    expect(html).toContain('Sí quedó: es este número');
    expect(html).toContain('value="con-502"');
    expect(html).not.toContain('Volver a crear');
    expect(html).not.toContain('No hay instalaciones esperando validación');
  });

  it('FALLIDA: dice el motivo y ofrece «Volver a crear»', () => {
    const html = pintar({ estado: 'fallida', por_revisar: false, se_puede_pedir: true,
                          detalle: 'Una persona revisó en el proveedor: el cliente no quedó creado.' });
    expect(html).toContain('La instalación NO quedó creada en el proveedor.');
    expect(html).toContain('Volver a crear');
  });
});
