import { describe, expect, it } from 'vitest';

import {
  cupoDeLaCuadrilla,
  pastillasDePersona,
  resumenDeLoSinBajar,
  quienLaAsigno,
  textoDelAviso,
  textoDeLaSiguiente,
  textoDelVencimiento,
  tonoDelVencimiento,
  textoDePrioridad,
  textoSinBajar
} from './dia-publicado.js';

describe('lo que la app de cada persona debería tener', () => {
  const dia = '2026-10-28';

  it('el nombre aparte, y órdenes, teléfono y última conexión como pastillas', () => {
    expect(
      pastillasDePersona(
        { nombre: 'Jeider Amell', ordenes: 2, telefono: false, ultimo_contacto: '2026-10-28T10:15:00-05:00' },
        dia
      )
    ).toEqual({
      nombre: 'Jeider Amell',
      pastillas: [
        { texto: '2 órdenes', falta: false },
        { texto: 'sin teléfono registrado', falta: true },
        { texto: 'última conexión 10:15', falta: false }
      ]
    });
  });

  it('con teléfono no lo menciona; de otro día lleva la fecha; nunca conectado lo dice', () => {
    expect(
      pastillasDePersona({ nombre: 'Ana', ordenes: 1, telefono: true, ultimo_contacto: '2026-10-27T18:02:00-05:00' }, dia)
    ).toEqual({
      nombre: 'Ana',
      pastillas: [
        { texto: '1 orden', falta: false },
        { texto: 'última conexión 27/10 18:02', falta: false }
      ]
    });
    expect(pastillasDePersona({ nombre: 'Luis', ordenes: 0, telefono: true, ultimo_contacto: null }, dia)).toEqual({
      nombre: 'Luis',
      pastillas: [
        { texto: '0 órdenes', falta: false },
        { texto: 'nunca se conectó', falta: true }
      ]
    });
  });

  //  CUÁL ES EL PROBLEMA, Y CUÁL NO (07/11/2026). La frase anterior pintaba
  //  los cinco datos del mismo gris: «sin teléfono registrado» y «2 órdenes»
  //  pesaban igual. `falta` es lo único que la pantalla usa para el rojo, así
  //  que afirmar sobre él es afirmar sobre lo que se ve.
  it('solo lo que hay que atender queda marcado como falta', () => {
    const malo = pastillasDePersona(
      { nombre: 'Luis', ordenes: 3, telefono: false, ultimo_contacto: null, sin_bajar: 3 },
      dia
    );
    expect(malo.pastillas.filter((b) => b.falta).map((b) => b.texto)).toEqual([
      '3 sin bajar a su app',
      'sin teléfono registrado',
      'nunca se conectó'
    ]);

    const sano = pastillasDePersona(
      { nombre: 'Ana', ordenes: 3, telefono: true, ultimo_contacto: '2026-10-28T10:15:00-05:00', sin_bajar: 0 },
      dia
    );
    expect(sano.pastillas.some((b) => b.falta)).toBe(false);
    expect(sano.pastillas).toHaveLength(2);
  });

  it('lo asignado después de la última conexión, y nada si no hay', () => {
    expect(textoSinBajar({ sin_bajar: 0 })).toBe('');
    expect(textoSinBajar({ sin_bajar: 1 })).toBe('1 sin bajar a su app');
    expect(textoSinBajar({ sin_bajar: 3 })).toBe('3 sin bajar a su app');
  });

  //  EL MURO ROJO (07/11/2026). El usuario, con la captura: «qué otro arreglo
  //  se puede hacer para que no se vea tan maluco». La frase entera salía en
  //  CADA tarjeta —cuatro párrafos rojos idénticos de dos renglones— y cuatro
  //  avisos iguales no avisan: el rojo deja de marcar nada.
  it('la marca de la tarjeta es corta: el párrafo entero ya no se repite', () => {
    const corto = textoSinBajar({ sin_bajar: 10 });
    expect(corto).not.toContain('Que abra la app');
    expect(corto).not.toContain('última conexión');
    expect(corto.length).toBeLessThan(25);
  });

  it('pero el porqué y el qué hacer se siguen diciendo, UNA vez y arriba', () => {
    const r = resumenDeLoSinBajar([
      { personas: [{ sin_bajar: 10 }] },
      //  DOS personas de la MISMA cuadrilla con pendientes: una cuadrilla,
      //  siete órdenes. Sumar solo la primera es el error silencioso.
      { personas: [{ sin_bajar: 4 }, { sin_bajar: 3 }] },
      { personas: [{ sin_bajar: 0 }] }
    ]);
    expect(r).toBe('2 cuadrillas no abrieron la app: 17 órdenes todavía no están en los teléfonos. Que abran la app para recibirlas.');
  });

  it('una sola cuadrilla y una sola orden van en singular', () => {
    expect(resumenDeLoSinBajar([{ personas: [{ sin_bajar: 1 }] }]))
      .toBe('1 cuadrilla no abrió la app: 1 orden todavía no está en el teléfono. Que abran la app para recibirlas.');
  });

  it('si todas bajaron, no se dice nada: un aviso siempre visible no es un aviso', () => {
    expect(resumenDeLoSinBajar([{ personas: [{ sin_bajar: 0 }] }, { personas: [] }])).toBe('');
    expect(resumenDeLoSinBajar([])).toBe('');
    expect(resumenDeLoSinBajar(undefined)).toBe('');
  });
});

describe('cuántas órdenes tiene la cuadrilla y cuántas le caben', () => {
  //  EL DEFECTO, en la captura del 07/11/2026: la cabecera armaba
  //  «${cuantas} de ${tope} órdenes» sin mirar los números, y la Cuadrilla #3
  //  decía «20 de 10 órdenes». Se lee como una pantalla rota, y lo que de
  //  verdad pasa --que tiene el doble de lo que le cabe-- queda escondido.
  it('EL DEFECTO: pasada de cupo no dice «20 de 10»', () => {
    const c = cupoDeLaCuadrilla(20, 10);
    expect(c.texto).not.toContain('20 de 10');
    expect(c.texto).toBe('20 órdenes · 10 sobre el tope de 10');
    expect(c.pasada).toBe(true);
  });

  it('por una sola orden de más también lo dice', () => {
    expect(cupoDeLaCuadrilla(11, 10).texto).toBe('11 órdenes · 1 sobre el tope de 10');
  });

  //  EL CONTROL: lo normal tiene que seguir leyéndose igual que siempre.
  it('dentro del cupo, y justo en el cupo, se lee como antes', () => {
    expect(cupoDeLaCuadrilla(4, 10)).toEqual({ texto: '4 de 10 órdenes', pasada: false });
    expect(cupoDeLaCuadrilla(10, 10)).toEqual({ texto: '10 de 10 órdenes', pasada: false });
    //  El plural va con el TOPE: «1 de 10 orden» está mal escrito.
    expect(cupoDeLaCuadrilla(1, 10).texto).toBe('1 de 10 órdenes');
    expect(cupoDeLaCuadrilla(1, 1).texto).toBe('1 de 1 orden');
  });

  it('sin tope no inventa uno', () => {
    expect(cupoDeLaCuadrilla(7, 0)).toEqual({ texto: '7 órdenes', pasada: false });
    expect(cupoDeLaCuadrilla(7, undefined).texto).toBe('7 órdenes');
    expect(cupoDeLaCuadrilla(1, null).texto).toBe('1 orden');
  });

  it('sin órdenes no se marca en rojo', () => {
    expect(cupoDeLaCuadrilla(0, 10)).toEqual({ texto: '0 de 10 órdenes', pasada: false });
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

describe('la siguiente de la cuadrilla (29/10/2026)', () => {
  it('sin nada empezado, empieza por esta; con algo en marcha o hecho, sigue esta', () => {
    expect(textoDeLaSiguiente([{ estado: 'asignada' }, { estado: 'asignada' }])).toBe('Empieza por esta');
    for (const estado of ['en_camino', 'en_sitio', 'completada_campo', 'cerrada']) {
      expect(textoDeLaSiguiente([{ estado }, { estado: 'asignada' }])).toBe('Sigue esta');
    }
    expect(textoDeLaSiguiente([])).toBe('Empieza por esta');
  });
});

describe('cuándo vence, contra el día que se mira (29/10/2026)', () => {
  const dia = '2026-10-29';

  it('hoy, mañana, otro día y lo vencido', () => {
    expect(
      [
        '2026-10-29T23:59:59-05:00',
        '2026-10-30T23:59:59-05:00',
        '2026-11-03T23:59:59-05:00',
        '2026-10-28T23:59:59-05:00'
      ].map((v) => textoDelVencimiento(v, dia))
    ).toEqual(['Vence hoy', 'Vence mañana', 'Vence el 03/11', 'Venció el 28/10']);
  });

  it('el día es el de la empresa, no el del navegador ni el de UTC', () => {
    //  23:59 en Bogotá es el 04:59 UTC del día siguiente: sigue siendo «hoy».
    expect(textoDelVencimiento('2026-10-29T23:59:59-05:00', dia)).toBe('Vence hoy');
  });

  it('el tono dice lo mismo que el texto: rojo lo vencido, ámbar lo de hoy', () => {
    expect(
      [
        '2026-10-28T23:59:59-05:00',
        '2026-10-29T23:59:59-05:00',
        '2026-10-30T23:59:59-05:00',
        '2026-11-03T23:59:59-05:00',
        null
      ].map((v) => tonoDelVencimiento(v, dia))
    ).toEqual(['vencida', 'hoy', 'proxima', 'proxima', 'sin']);
  });

  it('sin fecha no inventa', () => {
    expect([null, undefined, '', 'mañana'].map((v) => textoDelVencimiento(v, dia))).toEqual([
      'Sin vencimiento',
      'Sin vencimiento',
      'Sin vencimiento',
      'Sin vencimiento'
    ]);
  });
});
