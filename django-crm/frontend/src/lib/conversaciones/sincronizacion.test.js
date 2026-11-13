/**
 * Lo que quedó sin hacer afuera (B4).
 *
 * La aserción que más importa: `desconocida` no puede leerse como «falló». Si
 * la pantalla dice que falló, alguien va a rehacerlo — y rehacer un ticket que
 * quizá ya existe manda dos visitas técnicas al mismo cliente.
 */
import { describe, it, expect } from 'vitest';
import {
  lineaDeSincronizacion, estadoDeSincronizacion, nombreDeEfecto,
  loQueEsperaRevision, hayQueRevisar
} from './sincronizacion.js';

const s = (extra) => ({
  tipo: 'crear_caso', estado: 'pendiente', intentos: 1,
  creado_en: '2026-09-20T10:00:00Z', actualizado_en: '2026-09-20T10:05:00Z', ...extra
});

describe('desconocida no es un fallo', () => {
  it('no dice que falló: dice que no se sabe', () => {
    const d = lineaDeSincronizacion(s({ estado: 'desconocida', tipo: 'crear_ticket' }));
    expect(d.texto).toMatch(/no sabemos si llegó a hacerse/i);
    expect(d.texto).not.toMatch(/fall|no se pudo|error/i);
  });

  it('y explica por qué no se reintenta solo', () => {
    const d = lineaDeSincronizacion(s({ estado: 'desconocida' }));
    expect(d.detalle).toMatch(/duplicaría el trabajo|comprobarlo a mano/i);
  });

  it('va en ámbar, no en rojo: rojo empujaría a rehacerlo', () => {
    expect(lineaDeSincronizacion(s({ estado: 'desconocida' })).tono).toBe('aviso');
    expect(lineaDeSincronizacion(s({ estado: 'fallida_definitiva' })).tono).toBe('mal');
  });

  it('y no comparte texto con un fallo definitivo', () => {
    const d = lineaDeSincronizacion(s({ estado: 'desconocida' }));
    const f = lineaDeSincronizacion(s({ estado: 'fallida_definitiva' }));
    expect(d.texto).not.toBe(f.texto);
    expect(f.texto).toMatch(/no se pudo/i);
  });
});

describe('qué espera a una persona', () => {
  it('las dos terminales que nadie va a reintentar', () => {
    for (const estado of ['desconocida', 'fallida_definitiva']) {
      expect(estadoDeSincronizacion({ estado }).revisar).toBe(true);
    }
  });

  it('lo que sigue en cola NO pide revisión: se reintenta solo', () => {
    for (const estado of ['pendiente', 'en_curso', 'hecha']) {
      expect(estadoDeSincronizacion({ estado }).revisar).toBe(false);
    }
  });

  it('hayQueRevisar detecta una sola entre varias sanas', () => {
    expect(hayQueRevisar([s({ estado: 'hecha' }), s({ estado: 'pendiente' })])).toBe(false);
    expect(hayQueRevisar([s({ estado: 'hecha' }), s({ estado: 'desconocida' })])).toBe(true);
  });
});

describe('el panel dice qué falta, no qué se hizo', () => {
  it('lo ya hecho no se lista', () => {
    const lista = [s({ estado: 'hecha' }), s({ estado: 'desconocida' })];
    expect(loQueEsperaRevision(lista)).toHaveLength(1);
    expect(loQueEsperaRevision(lista)[0].estado).toBe('desconocida');
  });

  it('si todo salió bien, no hay nada que mostrar', () => {
    expect(loQueEsperaRevision([s({ estado: 'hecha' }), s({ estado: 'hecha' })])).toHaveLength(0);
  });
});

describe('el resto de la línea', () => {
  it('los cuatro tipos del contrato tienen nombre', () => {
    for (const tipo of ['crear_caso', 'crear_ticket', 'cerrar_caso', 'cerrar_ticket']) {
      expect(nombreDeEfecto(tipo)).not.toBe(tipo.replaceAll('_', ' '));
    }
  });

  it('un tipo nuevo se muestra, no se esconde', () => {
    expect(nombreDeEfecto('algo_nuevo')).toBe('algo nuevo');
  });

  it('los intentos sólo aparecen a partir del segundo', () => {
    expect(lineaDeSincronizacion(s({ intentos: 1 })).intentos).toBeNull();
    expect(lineaDeSincronizacion(s({ intentos: 3 })).intentos).toBe('intento 3');
  });

  it('un registro vacío no rompe ni inventa', () => {
    expect(() => lineaDeSincronizacion(null)).not.toThrow();
    expect(lineaDeSincronizacion(null).clave).toBe('sin_registro');
  });
});

describe('un cierre que espera una aprobación no es una falla (12/11/2026)', () => {
  it('pendiente por una regla de cierre: dice que espera una aprobación, sin contar intentos', () => {
    const d = lineaDeSincronizacion(
      s({ tipo: 'cerrar_caso', estado: 'pendiente', intentos: 5, ultimo_error_codigo: 'espera_aprobacion' }));
    expect(d.texto).toMatch(/aprobación/i);
    expect(d.texto).not.toMatch(/reintenta|no se pudo/i);
    expect(d.intentos).toBeNull();
    expect(d.revisar).toBe(false);
  });

  it('rechazado: es una decisión, no un error a revisar', () => {
    const d = lineaDeSincronizacion(
      s({ tipo: 'cerrar_caso', estado: 'fallida_definitiva', ultimo_error_codigo: 'cierre_rechazado' }));
    expect(d.texto).toMatch(/rechazaron el cierre/i);
    expect(d.texto).not.toMatch(/no se pudo/i);
    expect(hayQueRevisar([
      s({ estado: 'fallida_definitiva', ultimo_error_codigo: 'cierre_rechazado' })
    ])).toBe(false);
  });

  it('un código desconocido no cambia nada: manda el estado', () => {
    const d = lineaDeSincronizacion(s({ estado: 'fallida_definitiva', ultimo_error_codigo: 'http_400' }));
    expect(d.texto).toMatch(/no se pudo/i);
    expect(estadoDeSincronizacion(s({ estado: 'pendiente', ultimo_error_codigo: '__proto__' })).clave)
      .toBe('pendiente');
  });
});
