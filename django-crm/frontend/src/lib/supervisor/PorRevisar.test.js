import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import PorRevisar from './PorRevisar.svelte';

/**
 * POR REVISAR (31/10/2026). En producción la OT #4, terminada el 30 y sin
 * aprobar, el 31 no salía en ningún lado. Se mide lo que se dibuja, con la
 * forma de `campo/dia_publicado.py` (`por_revisar`).
 */
const DIA = '2026-10-31';
const revision = {
  veredicto: 'se_puede_cerrar',
  texto: 'Se puede cerrar',
  solucion: 'Cambié el conector',
  puntos: [{ clave: 'checklist', ok: true, texto: 'El checklist está completo.' }],
  evidencias: [],
  sugeridas: []
};
const orden = (extra = {}) => ({
  id: 'o-4', numero: 4, vuelta: 1, estado: 'completada_campo', estado_texto: 'Completada en campo',
  asunto: 'Instalación Tdt', cliente: 'X', barrio: '', tecnicos: ['Jeider Amell'],
  validacion: 'pendiente', validacion_texto: 'Pendiente de validación',
  revision, terminada_el: '30/10 17:42', ...extra
});
const html = (ordenes) => render(PorRevisar, { props: { ordenes, dia: DIA } }).body;

describe('por revisar, de días anteriores', () => {
  it('la orden de ayer sale con cuándo terminó, la revisión y sus botones', () => {
    const h = html([orden()]);

    expect(h).toContain('Por revisar, de días anteriores (1)');
    expect(h).toContain('OT 4');
    expect(h).toContain('Terminó el 30/10 17:42');
    expect(h).toContain('Se puede cerrar');
    expect(h).toContain('action="?/aprobar"');
    expect(h).toContain('Devolver al técnico');
  });

  it('la aprobada que quedó sin cerrar ofrece Cerrar', () => {
    const h = html([orden({ revision: null, validacion: 'aprobado', validacion_texto: 'Aprobado' })]);

    expect(h).toContain('action="?/cerrar"');
    expect(h).not.toContain('action="?/aprobar"');
  });

  it('dice si el Supervisor le recordó reportar, y si llegó al teléfono', () => {
    const h = html([orden({ recordatorios: [
      { cuando: '30/10 16:05', llego: true },
      { cuando: '30/10 16:50', llego: false }
    ] })]);

    expect(h).toContain('El Supervisor le recordó reportar · 30/10 16:05');
    expect(h).toContain('El Supervisor le recordó reportar · 30/10 16:50 (no llegó al teléfono)');
    expect(h.match(/no llegó al teléfono/g)).toHaveLength(1);
    expect(html([orden()])).not.toContain('le recordó reportar');
  });

  it('sin nada que revisar, la sección no se dibuja', () => {
    expect(html([])).not.toContain('Por revisar');
    expect(html(undefined)).not.toContain('Por revisar');
  });
});
