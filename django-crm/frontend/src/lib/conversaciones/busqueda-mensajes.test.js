import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  debeBuscarEnMensajes,
  partirPorCoincidencia,
  resultadosDeLaVista,
  crearBuscadorMensajes,
  ESPERA_ENTRE_TECLAS_MS
} from './busqueda-mensajes.js';

/**
 * Buscar en los mensajes, del lado de la pantalla (11/11/2026): cuándo se
 * pregunta, el resaltado sin HTML, la vista de canales, y el que espera entre
 * teclas -- que no mande un pedido por letra ni pinte una respuesta vieja.
 */

describe('cuándo se le pregunta al motor', () => {
  it('de 3 a 100 letras, sin contar los espacios de más', () => {
    expect(debeBuscarEnMensajes('ab')).toBe(false);
    expect(debeBuscarEnMensajes('   ab   ')).toBe(false);
    // El espacio de adentro SÍ cuenta, igual que en el motor: «a b» son 3.
    expect(debeBuscarEnMensajes('  a   b  ')).toBe(true);
    expect(debeBuscarEnMensajes('abc')).toBe(true);
    expect(debeBuscarEnMensajes('x'.repeat(100))).toBe(true);
    expect(debeBuscarEnMensajes('x'.repeat(101))).toBe(false);
    expect(debeBuscarEnMensajes(null)).toBe(false);
  });
});

describe('resaltar partiendo el texto, nunca con HTML', () => {
  it('marca cada coincidencia sin importar mayúsculas', () => {
    expect(partirPorCoincidencia('El POSTE cayó, el poste sigue', 'poste')).toEqual([
      { texto: 'El ', coincide: false },
      { texto: 'POSTE', coincide: true },
      { texto: ' cayó, el ', coincide: false },
      { texto: 'poste', coincide: true },
      { texto: ' sigue', coincide: false }
    ]);
  });

  it('lo buscado con caracteres de regex se busca literal', () => {
    expect(partirPorCoincidencia('recargo del 50% (mensual)', '50% (m')).toEqual([
      { texto: 'recargo del ', coincide: false },
      { texto: '50% (m', coincide: true },
      { texto: 'ensual)', coincide: false }
    ]);
  });

  it('el marcado que escribió un cliente queda como texto, en un trozo más', () => {
    const partes = partirPorCoincidencia('<img src=x onerror=alert(1)> poste', 'poste');
    expect(partes[0]).toEqual({ texto: '<img src=x onerror=alert(1)> ', coincide: false });
    expect(partes.map((p) => p.texto).join('')).toBe('<img src=x onerror=alert(1)> poste');
  });

  it('un espacio de la búsqueda vale por cualquier blanco del texto', () => {
    const partes = partirPorCoincidencia('poste\n  caído', 'poste caído');
    expect(partes).toEqual([{ texto: 'poste\n  caído', coincide: true }]);
  });

  it('sin coincidencia, el texto entero sin marcar', () => {
    expect(partirPorCoincidencia('nada que ver', 'poste')).toEqual([{ texto: 'nada que ver', coincide: false }]);
  });
});

describe('la vista de canales', () => {
  const R = [{ canal_operativo: true }, { canal_operativo: false }, {}];
  it('la misma regla que la cola: sin el dato, no se esconde', () => {
    expect(resultadosDeLaVista(R, 'operativo')).toEqual([R[0], R[2]]);
    expect(resultadosDeLaVista(R, 'pruebas')).toEqual([R[1], R[2]]);
    expect(resultadosDeLaVista(R, 'todos')).toEqual(R);
  });
});

describe('el que espera entre teclas', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  /** @param {(q: string, signal: AbortSignal, vista: string) => Promise<any>} buscar */
  const armar = (buscar) => {
    /** @type {any[]} */
    const estados = [];
    const b = crearBuscadorMensajes({ buscar, alCambiar: (e) => estados.push(e) });
    return { b, estados, ultimo: () => estados[estados.length - 1] };
  };

  it('EL EFECTO: escribir «poste» de corrido manda UN pedido, el de la palabra entera', async () => {
    const buscar = vi.fn(async (q) => ({ resultados: [{ mensaje_id: q }], tope: 30 }));
    const { b, ultimo } = armar(buscar);
    for (const q of ['pos', 'post', 'poste']) {
      b.pedir(q);
      await vi.advanceTimersByTimeAsync(100);
    }
    expect(buscar).not.toHaveBeenCalled();
    expect(ultimo().estado).toBe('buscando');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    expect(buscar).toHaveBeenCalledTimes(1);
    expect(buscar.mock.calls[0][0]).toBe('poste');
    expect(ultimo()).toEqual({ estado: 'listo', q: 'poste', resultados: [{ mensaje_id: 'poste' }], tope: 30, error: '' });
  });

  it('una respuesta vieja que llega tarde no pisa a la nueva, y su pedido se cancela', async () => {
    /** @type {Record<string, (v: any) => void>} */
    const pendientes = {};
    /** @type {AbortSignal[]} */
    const señales = [];
    const { b, ultimo } = armar(
      (q, signal) =>
        new Promise((resolver) => {
          señales.push(signal);
          pendientes[q] = resolver;
        })
    );
    b.pedir('pos');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    b.pedir('poste');
    expect(señales[0].aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    pendientes.poste({ resultados: [{ mensaje_id: 'nuevo' }] });
    await vi.advanceTimersByTimeAsync(0);
    pendientes.pos({ resultados: [{ mensaje_id: 'viejo' }] });
    await vi.advanceTimersByTimeAsync(0);
    expect(ultimo().resultados).toEqual([{ mensaje_id: 'nuevo' }]);
  });

  it('borrar hasta menos de 3 letras vuelve a inactivo y no pregunta', async () => {
    const buscar = vi.fn(async () => ({ resultados: [] }));
    const { b, ultimo } = armar(buscar);
    b.pedir('poste');
    b.pedir('po');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS * 2);
    expect(buscar).not.toHaveBeenCalled();
    expect(ultimo().estado).toBe('inactivo');
  });

  it('un error del motor queda como estado de error, con su texto', async () => {
    const { b, ultimo } = armar(async () => {
      throw new Error('el asistente no contestó');
    });
    b.pedir('poste');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    expect(ultimo()).toMatchObject({ estado: 'error', q: 'poste', error: 'el asistente no contestó' });
  });

  it('la vista de canales viaja con la búsqueda (11/11/2026, auditoría H2)', async () => {
    const buscar = vi.fn(async () => ({ resultados: [] }));
    const { b } = armar(buscar);
    b.pedir('poste', 'operativo');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    expect(buscar).toHaveBeenCalledTimes(1);
    expect(buscar.mock.calls[0][2]).toBe('operativo');
  });

  it('EL EFECTO: cambiar la vista con la búsqueda escrita la repite con la vista nueva', async () => {
    const buscar = vi.fn(async (_q, _s, vista) => ({ resultados: [{ vista }] }));
    const { b, ultimo } = armar(buscar);
    b.pedir('poste', 'operativo');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    // El mismo texto y la misma vista no vuelven a preguntar...
    b.pedir('poste', 'operativo');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    expect(buscar).toHaveBeenCalledTimes(1);
    // ...pero otra vista sí: los 30 de una no son los de la otra.
    b.pedir('poste', 'pruebas');
    expect(ultimo().estado).toBe('buscando');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    expect(buscar).toHaveBeenCalledTimes(2);
    expect(buscar.mock.calls[1][2]).toBe('pruebas');
    expect(ultimo()).toMatchObject({ estado: 'listo', resultados: [{ vista: 'pruebas' }] });
  });

  it('cambiar la vista con una búsqueda EN CURSO corta la vieja y pregunta por la nueva', async () => {
    /** @type {AbortSignal[]} */
    const señales = [];
    /** @type {((v: any) => void)[]} */
    const resolvers = [];
    const { b, ultimo } = armar(
      (_q, signal) =>
        new Promise((r) => {
          señales.push(signal);
          resolvers.push(r);
        })
    );
    b.pedir('poste', 'operativo');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    b.pedir('poste', 'todos');
    expect(señales[0].aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    resolvers[1]({ resultados: [{ mensaje_id: 'de-todos' }] });
    await vi.advanceTimersByTimeAsync(0);
    resolvers[0]({ resultados: [{ mensaje_id: 'de-operativo' }] });
    await vi.advanceTimersByTimeAsync(0);
    expect(ultimo().resultados).toEqual([{ mensaje_id: 'de-todos' }]);
  });

  it('cancelar al desmontar: nada escribe después', async () => {
    /** @type {(v: any) => void} */
    let resolver = () => {};
    const { b, estados } = armar(() => new Promise((r) => (resolver = r)));
    b.pedir('poste');
    await vi.advanceTimersByTimeAsync(ESPERA_ENTRE_TECLAS_MS);
    const antes = estados.length;
    b.cancelar();
    resolver({ resultados: [{ mensaje_id: 'tarde' }] });
    await vi.advanceTimersByTimeAsync(0);
    expect(estados.length).toBe(antes);
  });
});
