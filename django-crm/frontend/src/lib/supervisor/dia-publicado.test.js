import { describe, expect, it } from 'vitest';

import { quienLaAsigno, textoDelAviso, textoDePrioridad } from './dia-publicado.js';

describe('quién asignó una orden, como lo lee una persona', () => {
  const dia = '2026-10-28';

  it('el Supervisor, con la hora del reloj de la empresa', () => {
    expect(
      quienLaAsigno(
        { asignada_por: 'supervisor', asignada_por_nombre: 'Supervisor', asignada_en: '2026-10-28T09:07:31-05:00' },
        dia
      )
    ).toBe('Supervisor · 09:07');
  });

  it('una persona, con su nombre', () => {
    expect(
      quienLaAsigno(
        { asignada_por: 'persona', asignada_por_nombre: 'Mayra', asignada_en: '2026-10-28T08:15:00-05:00' },
        dia
      )
    ).toBe('Mayra · 08:15');
  });

  it('si fue otro día, lo dice con la fecha', () => {
    expect(
      quienLaAsigno(
        { asignada_por: 'supervisor', asignada_por_nombre: 'Supervisor', asignada_en: '2026-10-27T18:07:00-05:00' },
        dia
      )
    ).toBe('Supervisor · 27/10 18:07');
  });

  it('sin evento no adivina', () => {
    expect(quienLaAsigno({ asignada_por: '', asignada_en: null }, dia)).toBe('Sin registro');
  });
});

describe('el aviso y la prioridad', () => {
  it('cada estado del aviso dice lo suyo', () => {
    expect(['avisado', 'sin_aviso', 'sin_telefono'].map(textoDelAviso)).toEqual([
      'Avisado',
      'Sin aviso',
      'Sin teléfono registrado'
    ]);
  });

  it('la prioridad en palabras', () => {
    expect(['alta', 'media', 'baja', ''].map(textoDePrioridad)).toEqual(['Alta', 'Media', 'Baja', '—']);
  });
});
