import { describe, expect, it } from 'vitest';

import {
  lineaDePersona,
  quienLaAsigno,
  textoDelAviso,
  textoDePrioridad,
  textoSinBajar
} from './dia-publicado.js';

describe('lo que la app de cada persona debería tener', () => {
  const dia = '2026-10-28';

  it('órdenes, teléfono y última conexión', () => {
    expect(
      lineaDePersona(
        { nombre: 'Jeider Amell', ordenes: 2, telefono: false, ultimo_contacto: '2026-10-28T10:15:00-05:00' },
        dia
      )
    ).toBe('Jeider Amell: 2 órdenes · sin teléfono registrado · última conexión 10:15');
  });

  it('con teléfono no lo menciona; de otro día lleva la fecha; nunca conectado lo dice', () => {
    expect(
      lineaDePersona({ nombre: 'Ana', ordenes: 1, telefono: true, ultimo_contacto: '2026-10-27T18:02:00-05:00' }, dia)
    ).toBe('Ana: 1 orden · última conexión 27/10 18:02');
    expect(lineaDePersona({ nombre: 'Luis', ordenes: 0, telefono: true, ultimo_contacto: null }, dia)).toBe(
      'Luis: 0 órdenes · nunca se conectó'
    );
  });

  it('lo asignado después de la última conexión, y nada si no hay', () => {
    expect(textoSinBajar({ sin_bajar: 0 })).toBe('');
    expect(textoSinBajar({ sin_bajar: 1 })).toContain('1 asignada después');
    expect(textoSinBajar({ sin_bajar: 3 })).toContain('3 asignadas después');
  });
});

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
    expect(['avisado', 'no_llego', 'sin_aviso', 'sin_telefono'].map(textoDelAviso)).toEqual([
      'Enviado al teléfono',
      'No llegó al teléfono',
      'Sin aviso',
      'Sin teléfono registrado'
    ]);
  });

  it('la prioridad en palabras', () => {
    expect(['alta', 'media', 'baja', ''].map(textoDePrioridad)).toEqual(['Alta', 'Media', 'Baja', '—']);
  });
});
