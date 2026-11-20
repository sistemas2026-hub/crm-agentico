/**
 * Guarda de `afinar_instruccion.js`.
 *
 * Lo que afirma no es que las funciones existan: es lo que, si se rompe,
 * manda a alguien a reescribir una instrucción que estaba bien, o le hace
 * creer que una mala sirve.
 */
import { describe, expect, it } from 'vitest';

import {
  MAX_INSTRUCCION,
  cuerpoDePrueba,
  queSignifica,
  sePuedeProbar,
  veredicto
} from './afinar_instruccion.js';

describe('sePuedeProbar — cada prueba cuesta una llamada al modelo', () => {
  it('un texto vacío no gasta nada', () => {
    expect(sePuedeProbar('   ').puede).toBe(false);
  });

  it('más largo que el campo de la plantilla no se prueba', () => {
    //  Aprobar un texto que después no entra en el campo es aprobar nada.
    const r = sePuedeProbar('x'.repeat(MAX_INSTRUCCION + 1));
    expect(r.puede).toBe(false);
    expect(r.motivo).toContain(String(MAX_INSTRUCCION));
  });

  it('justo en el límite SÍ se prueba', () => {
    //  El borde se afirma en los dos lados: si solo se probara el de arriba,
    //  un `>=` en vez de `>` pasaría sin que nadie lo note.
    expect(sePuedeProbar('x'.repeat(MAX_INSTRUCCION)).puede).toBe(true);
  });

  it('el texto que ya está guardado no se vuelve a probar', () => {
    const r = sePuedeProbar('  Los tres numeros  ', 'Los tres numeros');
    expect(r.puede).toBe(false);
    expect(r.motivo).toContain('ya está guardado');
  });

  it('pero un cambio real sí', () => {
    expect(sePuedeProbar('Los tres numeros del test', 'Velocidad contratada').puede).toBe(true);
  });
});

describe('veredicto — tres valores, no dos', () => {
  it('«no se sabe» NO se muestra como un rechazo', () => {
    //  EL CASO QUE YA PASÓ. El 06/11/2026 un parser binario leyó
    //  «MUESTRA: no se sabe» como un «no» y dio un veredicto falso.
    const duda = veredicto(null);
    expect(duda.clase).toBe('duda');
    expect(duda.clase).not.toBe('no');
    expect(duda.texto).toContain('no puede afirmar');
  });

  it('undefined se trata como duda, no como rechazo', () => {
    //  Una respuesta sin el campo no es un «no»: es que no se sabe.
    expect(veredicto(undefined).clase).toBe('duda');
  });

  it('los tres son distintos entre sí', () => {
    const clases = [veredicto(true), veredicto(false), veredicto(null)].map((v) => v.clase);
    expect(new Set(clases).size).toBe(3);
  });
});

describe('queSignifica — ayuda a leer, no decide', () => {
  it('foto buena + lo ve = el texto viejo era el problema', () => {
    expect(queSignifica(true, true)).toContain('el texto anterior era el problema');
  });

  it('foto buena + no lo ve = probá otra redacción', () => {
    expect(queSignifica(null, true)).toContain('otra redacción');
    expect(queSignifica(false, true)).toContain('otra redacción');
  });

  it('foto MALA + la aprueba = avisa que el texto quedó laxo', () => {
    //  El caso peligroso: una redacción que aprueba cualquier cosa se vería
    //  como un éxito si nadie lo señala.
    expect(queSignifica(true, false)).toContain('demasiado laxo');
  });

  it('foto mala + la rechaza = eso es lo que se busca', () => {
    expect(queSignifica(false, false)).toContain('es lo que se busca');
  });
});

describe('cuerpoDePrueba', () => {
  it('manda el texto sin espacios de más', () => {
    expect(cuerpoDePrueba('  hola  ')).toEqual({ instrucciones: 'hola' });
  });
});
