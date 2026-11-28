/**
 * T6 leído desde la pantalla (fase 1.4C).
 *
 * Lo que protege: que la Bandeja no le diga al operador algo que Dexter no
 * sabe. Las aserciones que importan son las negativas —un resultado incierto
 * NO puede mostrarse como fallo, y un envío que no volvió a la IA NO puede
 * mostrarse como devuelto—, porque las dos empujan al mismo error: reintentar
 * un mensaje que quizá ya salió, y que el cliente lo reciba dos veces.
 */
import { describe, it, expect } from 'vitest';
import { estadoDeDevolucion, sePuedeReintentar, SIN_CONFIRMAR } from './devolucion.js';

const r = (datos, ok = true) => estadoDeDevolucion({ pedida: true, ok, datos });

describe('cuando no se pidió devolver', () => {
  it('no hay nada que decir', () => {
    expect(estadoDeDevolucion({ pedida: false, ok: true, datos: { resultado: 'aceptado' } }))
      .toBeNull();
    expect(estadoDeDevolucion({})).toBeNull();
  });
});

describe('el único caso que se puede afirmar', () => {
  it('devuelto_al_asistente true: la conversación volvió a la IA', () => {
    const a = r({ devuelto_al_asistente: true, resultado: 'aceptado' });
    expect(a.estado).toBe('devuelta');
    expect(a.tono).toBe('ok');
  });

  it('y se afirma SOLO por esa bandera, no por el resultado de la entrega', () => {
    // Entrega aceptada pero el control no volvió: alguien soltó la
    // conversación entre el envío y el paso 4.
    const a = r({ devuelto_al_asistente: false, resultado: 'aceptado' });
    expect(a.estado).not.toBe('devuelta');
    expect(a.texto).toContain('no volvió a la IA');
  });
});

describe('lo que NO se puede afirmar', () => {
  it.each(SIN_CONFIRMAR)('%s no es un fallo', (resultado) => {
    const a = r({ devuelto_al_asistente: false, resultado });
    expect(a.estado).toBe('no_confirmada');
    expect(a.tono).toBe('aviso');          // ámbar, no rojo
    expect(a.tono).not.toBe('mal');
    expect(a.texto).not.toMatch(/no salió|falló/i);
  });

  it('solo un rechazo confirmado se dice como fallo', () => {
    const a = r({ devuelto_al_asistente: false, resultado: 'rechazado' });
    expect(a.estado).toBe('fallo');
    expect(a.tono).toBe('mal');
    expect(a.texto).toContain('no salió');
  });

  it('un error de transporte no afirma que el mensaje no salió', () => {
    const a = estadoDeDevolucion({ pedida: true, ok: false, datos: null });
    expect(a.estado).toBe('sin_respuesta');
    expect(a.texto).toMatch(/no sabemos/i);
    expect(a.texto).not.toMatch(/no salió/i);
  });

  it('una respuesta sin resultado tampoco se da por buena', () => {
    expect(r({}).estado).toBe('no_confirmada');
    expect(r(null, true).estado).toBe('sin_respuesta');
  });

  it('un resultado que esta pantalla no conoce cae en no confirmado', () => {
    expect(r({ resultado: 'algo_nuevo' }).estado).toBe('no_confirmada');
  });

  it('ningún texto promete más de lo que el motor sabe', () => {
    const textos = [
      ...SIN_CONFIRMAR.map((x) => r({ resultado: x }).texto),
      r({ resultado: 'rechazado' }).texto,
      estadoDeDevolucion({ pedida: true, ok: false }).texto
    ];
    for (const t of textos) {
      // Nada de "se revirtió sin problema" ni "traspaso registrado": son los
      // textos de la referencia visual, y afirman cosas que no constan.
      expect(t).not.toMatch(/revirti|revert|registrad[oa] el traspaso|sin problema/i);
      expect(t).toMatch(/tu cargo|no sabemos/i);
    }
  });
});

describe('reintentar', () => {
  it('solo ante un rechazo confirmado', () => {
    expect(sePuedeReintentar('fallo')).toBe(true);
  });

  it('nunca cuando el mensaje pudo haber salido', () => {
    for (const e of ['no_confirmada', 'sin_respuesta', 'entregada_sin_devolver', 'devuelta']) {
      expect(sePuedeReintentar(e)).toBe(false);
    }
  });
});
