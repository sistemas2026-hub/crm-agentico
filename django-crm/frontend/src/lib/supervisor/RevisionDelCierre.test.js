import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import OrdenDelDia from './OrdenDelDia.svelte';
import RevisionDelCierre from './RevisionDelCierre.svelte';
import { motivosDeLaRevision } from './dia-publicado.js';

/**
 * LO QUE DICE EL SUPERVISOR DEL CIERRE (30/10/2026,
 * SPEC/objetivos/revision-del-cierre.md). Con la forma de
 * `campo/revision_del_cierre.py`: indica, y la persona confirma.
 */
const revision = (extra = {}) => ({
  veredicto: 'se_puede_cerrar',
  texto: 'Se puede cerrar',
  solucion: 'Cambié el conector',
  puntos: [
    { clave: 'checklist', ok: true, texto: 'El checklist está completo: datos y fotos.' },
    { clave: 'servicio', ok: true, texto: 'El técnico afirma que el servicio quedó funcionando.' }
  ],
  evidencias: [{ id: 'foto_ont', titulo: 'Foto de la ONT' }],
  sugeridas: [],
  ...extra
});

const orden = (extra = {}) => ({
  id: 'o-3', numero: 3, vuelta: 1, estado: 'completada_campo', estado_texto: 'Completada en campo',
  asunto: 'Instalación Tdt', cliente: 'X', tecnicos: [], revision: revision(), ...extra
});

const html = (o) => render(RevisionDelCierre, { props: { orden: o } }).body;

describe('la revisión del cierre en la tarjeta', () => {
  it('dice el veredicto, qué hizo el técnico y cada punto', () => {
    const h = html(orden());
    expect(h).toContain('El Supervisor revisó el cierre:');
    expect(h).toContain('Se puede cerrar');
    expect(h).toContain('Qué hizo: «Cambié el conector»');
    expect(h).toContain('✔');
    expect(h).toContain('El técnico afirma que el servicio quedó funcionando.');
    expect(h).toMatch(/class="rc rc-se_puede_cerrar/);
  });

  it('las dos decisiones, con la orden y su vuelta', () => {
    const h = html(orden({ vuelta: 2 }));
    expect(h).toMatch(/action="\?\/aprobar"/);
    expect(h).toContain('Aprobar y cerrar');
    expect(h).toContain('Devolver al técnico');
    expect(h).toMatch(/name="orden" value="o-3"/);
    expect(h).toMatch(/name="vuelta" value="2"/);
  });

  it('un «no» se marca distinto de un «no se sabe»', () => {
    const h = html(orden({
      revision: revision({
        veredicto: 'no_cerrar', texto: 'No se cierra',
        puntos: [
          { clave: 'servicio', ok: false, texto: 'El técnico dice que el servicio NO quedó funcionando.' },
          { clave: 'material', ok: null, texto: 'No registró material ni confirmó que no usó.' }
        ]
      })
    }));
    expect(h).toMatch(/class="rc rc-no_cerrar/);
    expect(h).toMatch(/class="rc-punto-false[^"]*"><span[^>]*>✖<\/span> El técnico dice que el servicio NO/);
    expect(h).toMatch(/class="rc-punto-null[^"]*"><span[^>]*>\?<\/span> No registró material/);
  });

  it('si el Supervisor la quiso cerrar solo y no pudo, dice cuándo y por qué', () => {
    const h = html(orden({
      revision: revision({ supervisor_no_pudo: { hora: '14:10', detalle: 'NO_AUTORIZADA: B7_REQUERIDO: x' } })
    }));
    expect(h).toContain('El Supervisor la quiso cerrar solo a las 14:10 y el motor no lo dejó: NO_AUTORIZADA: B7_REQUERIDO: x');
    expect(html(orden())).not.toContain('quiso cerrar solo');
  });

  it('si no se sabe si el ISP la cerró, no dice «no lo dejó»', () => {
    const h = html(orden({
      revision: revision({ supervisor_no_pudo: { hora: '15:00', detalle: 'ESTADO_INCIERTO: ReadTimeout' } })
    }));
    expect(h).toContain('no se sabe si el ISP la cerró');
    expect(h).not.toContain('no lo dejó');
  });

  it('sin revisión no dibuja nada', () => {
    expect(html(orden({ revision: null }))).not.toContain('rc-');
  });

  it('en la tarjeta: lo que espera revisión NO se atenúa; lo ya revisado sí', () => {
    const tarjeta = (o) => render(OrdenDelDia, { props: { orden: o, dia: '2026-10-30' } }).body;
    expect(tarjeta(orden())).not.toMatch(/class="od[^"]*od-terminada/);
    expect(tarjeta(orden())).toContain('El Supervisor revisó el cierre:');
    expect(tarjeta(orden({ estado: 'cerrada', revision: null }))).toMatch(/class="od[^"]*od-terminada/);
  });
});

describe('el porqué de una devolución, ya escrito', () => {
  it('lo que no está bien o no se sabe, una línea por punto', () => {
    expect(motivosDeLaRevision({
      puntos: [
        { ok: true, texto: 'bien' },
        { ok: false, texto: 'Falta la foto de la ONT.' },
        { ok: null, texto: 'No registró material.' }
      ]
    })).toBe('Falta la foto de la ONT.\nNo registró material.');
    expect(motivosDeLaRevision(null)).toBe('');
  });
});
