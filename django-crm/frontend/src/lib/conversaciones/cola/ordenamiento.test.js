/**
 * El orden de la cola — la guarda de D18.
 *
 * QUÉ PROTEGE ESTO, EXACTAMENTE
 * -----------------------------
 * Que una escalada nueva sin dueño no quede enterrada detrás de decenas de
 * conversaciones viejas. Es el defecto que cerró B3.5/D18, y hasta acá no
 * tenía ninguna guarda en el frontend: la cola ordena con estas funciones, y
 * una lista mal ordenada SE VE PERFECTA. No hay forma de notarlo mirando la
 * pantalla, que es justo lo que hace peligrosa la componentización de 0B.
 *
 * Se prueba el módulo que `+layout.svelte` importa de verdad, no una copia.
 */
import { describe, it, expect } from 'vitest';
import { ordenar, porBanda, peso, bandaDe, esperaDesde } from './ordenamiento.js';

/** Las bandas de nucleo/relevo/proyeccion.py, con sus nombres. */
const BANDA = {
  CLIENTE_ESPERA: 1,
  SIN_ASIGNAR: 2,
  REVISAR_EVALUACION: 3,
  INTERNO_PENDIENTE: 4,
  EN_CURSO: 5,
  LEGADO: 6
};

const hace = (/** @type {number} */ dias) =>
  new Date(Date.now() - dias * 86400_000).toISOString();

/**
 * Una fila como la manda el motor. Por omisión es PENDIENTE —escalada, sin
 * atender, sin dueño, abierta— porque es el estado del que trata D18.
 */
function fila(/** @type {any} */ extra = {}) {
  return {
    id: Math.random().toString(36).slice(2),
    escalada_a_humano: true,
    atendida: false,
    tomada_por: null,
    estado: 'abierta',
    escalada_en: hace(1),
    actualizado_en: hace(1),
    ultimo_mensaje_en: hace(1),
    mensajes_tras_escalar: 0,
    ...extra
  };
}

const ids = (/** @type {any[]} */ l) => l.map((c) => c.id);

describe('D18 — una escalada nueva sin asignar no puede quedar enterrada', () => {
  it('45 legado antiguas + 1 escalada nueva → la nueva primero', () => {
    // El escenario real que cerró D18: la base tenía ~45 conversaciones
    // heredadas, todas más viejas que cualquier cosa nueva.
    const legado = Array.from({ length: 45 }, (_, i) =>
      fila({
        id: `legado-${i}`,
        banda: BANDA.LEGADO,
        es_legado: true,
        esperando_desde: hace(30 + i),
        escalada_en: hace(30 + i)
      })
    );
    const nueva = fila({
      id: 'escalada-nueva',
      banda: BANDA.SIN_ASIGNAR,
      esperando_desde: hace(0.01) // hace un rato
    });

    // Se mezcla para que no pueda pasar por casualidad del orden de entrada.
    const entrada = [...legado.slice(0, 20), nueva, ...legado.slice(20)];
    const salida = ordenar(entrada, 'recomendado');

    expect(salida[0].id).toBe('escalada-nueva');
    expect(salida).toHaveLength(46);
  });

  it('sigue primera aunque TODAS las legado esperen más que ella', () => {
    // La antigüedad no puede ganarle a la banda: ése era exactamente el bug.
    const legado = Array.from({ length: 45 }, (_, i) =>
      fila({ id: `legado-${i}`, banda: BANDA.LEGADO, esperando_desde: hace(100 + i) })
    );
    const nueva = fila({ id: 'nueva', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(0) });

    expect(ordenar([...legado, nueva], 'recomendado')[0].id).toBe('nueva');
  });
});

describe('las seis bandas mandan, en su orden', () => {
  it('banda 1 antes que banda 2', () => {
    const a = fila({ id: 'b1', banda: BANDA.CLIENTE_ESPERA, esperando_desde: hace(0) });
    const b = fila({ id: 'b2', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(99) });
    expect(ids(ordenar([b, a], 'recomendado'))).toEqual(['b1', 'b2']);
  });

  it('banda 2 antes que banda 3', () => {
    const a = fila({ id: 'b2', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(0) });
    const b = fila({ id: 'b3', banda: BANDA.REVISAR_EVALUACION, esperando_desde: hace(99) });
    expect(ids(ordenar([b, a], 'recomendado'))).toEqual(['b2', 'b3']);
  });

  it('el recorrido completo 1 → 6, con la espera al revés en cada una', () => {
    // Cada banda superior espera MENOS que la de abajo: si el orden saliera
    // por antigüedad en vez de por banda, saldría exactamente invertido.
    const filas = [1, 2, 3, 4, 5, 6].map((b) =>
      fila({ id: `banda-${b}`, banda: b, esperando_desde: hace(b) })
    );
    const revueltas = [filas[3], filas[0], filas[5], filas[2], filas[4], filas[1]];
    expect(ids(ordenar(revueltas, 'recomendado'))).toEqual([
      'banda-1', 'banda-2', 'banda-3', 'banda-4', 'banda-5', 'banda-6'
    ]);
  });

  it('una fila sin banda cae al 99 y va después de las seis', () => {
    const conBanda = fila({ id: 'b6', banda: BANDA.LEGADO, esperando_desde: hace(90) });
    const sinBanda = fila({ id: 'sin', esperando_desde: hace(90) });
    expect(bandaDe(sinBanda)).toBe(99);
    expect(ids(ordenar([sinBanda, conBanda], 'recomendado'))).toEqual(['b6', 'sin']);
  });
});

describe('dentro de la misma banda, el que más espera va primero', () => {
  it('ordena por esperando_desde ascendente', () => {
    const filas = [
      fila({ id: 'reciente', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(1) }),
      fila({ id: 'antigua', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(10) }),
      fila({ id: 'media', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(5) })
    ];
    expect(ids(ordenar(filas, 'recomendado'))).toEqual(['antigua', 'media', 'reciente']);
  });

  it('sin esperando_desde va al final de SU banda, no al final de la lista', () => {
    const sinFecha = fila({ id: 'sin-fecha', banda: BANDA.SIN_ASIGNAR });
    const conFecha = fila({ id: 'con-fecha', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(3) });
    const bandaPeor = fila({ id: 'legado', banda: BANDA.LEGADO, esperando_desde: hace(99) });
    expect(esperaDesde(sinFecha)).toBeNull();
    expect(ids(ordenar([bandaPeor, sinFecha, conFecha], 'recomendado'))).toEqual([
      'con-fecha', 'sin-fecha', 'legado'
    ]);
  });

  it('dos sin fecha en la misma banda empatan: porBanda devuelve 0', () => {
    const a = fila({ banda: BANDA.SIN_ASIGNAR });
    const b = fila({ banda: BANDA.SIN_ASIGNAR });
    expect(porBanda(a, b)).toBe(0);
    // Y el empate es determinista: Array.sort es estable desde ES2019, así
    // que conservan el orden de entrada.
    const entrada = [{ ...a, id: 'primera' }, { ...b, id: 'segunda' }];
    expect(ids(ordenar(entrada, 'recomendado'))).toEqual(['primera', 'segunda']);
  });
});

describe('lo que no espera a nadie no compite por el lugar de arriba', () => {
  it('una resuelta queda detrás de cualquier pendiente, tenga la banda que tenga', () => {
    const cerrada = fila({
      id: 'cerrada',
      estado: 'cerrada',
      banda: BANDA.CLIENTE_ESPERA,
      esperando_desde: hace(99)
    });
    const pendienteFila = fila({ id: 'pendiente', banda: BANDA.LEGADO, esperando_desde: hace(0) });
    expect(ids(ordenar([cerrada, pendienteFila], 'recomendado'))).toEqual([
      'pendiente', 'cerrada'
    ]);
  });
});

describe('peso() — el respaldo de antes de D18', () => {
  it('NO se usa cuando hay proyección: manda la banda', () => {
    // La de peso() alto (insiste y espera hace mucho) está en la peor banda.
    // Si peso() ganara, saldría primera. Es la forma del bug original.
    const pesada = fila({
      id: 'pesada',
      banda: BANDA.LEGADO,
      esperando_desde: hace(60),
      escalada_en: hace(60),
      mensajes_tras_escalar: 5,
      motivo_escalamiento: 'frustracion_detectada'
    });
    const liviana = fila({ id: 'liviana', banda: BANDA.SIN_ASIGNAR, esperando_desde: hace(0) });

    expect(peso(pesada)).toBeGreaterThan(peso(liviana));
    expect(ids(ordenar([pesada, liviana], 'recomendado'))).toEqual(['liviana', 'pesada']);
  });

  it('se usa cuando NINGUNA de las dos trae banda — un motor sin proyección', () => {
    const insiste = fila({
      id: 'insiste',
      escalada_en: hace(1),
      mensajes_tras_escalar: 3
    });
    const vieja = fila({ id: 'vieja', escalada_en: hace(20) });

    // Volver a escribir vale 30 días equivalentes: le gana a los 20 de la otra.
    expect(peso(insiste)).toBeGreaterThan(peso(vieja));
    expect(ids(ordenar([vieja, insiste], 'recomendado'))).toEqual(['insiste', 'vieja']);
  });

  it('basta que UNA traiga banda para que mande la proyección', () => {
    // La condición real es `typeof a.banda === 'number' || typeof b.banda`.
    const conBanda = fila({ id: 'con', banda: BANDA.CLIENTE_ESPERA, esperando_desde: hace(0) });
    const sinBanda = fila({ id: 'sin', escalada_en: hace(50), mensajes_tras_escalar: 9 });
    expect(peso(sinBanda)).toBeGreaterThan(peso(conBanda));
    expect(ids(ordenar([sinBanda, conBanda], 'recomendado'))).toEqual(['con', 'sin']);
  });

  it('lo que no está pendiente pesa -1', () => {
    expect(peso(fila({ estado: 'cerrada' }))).toBe(-1);
    expect(peso(fila({ tomada_por: 'ana' }))).toBe(-1);
  });

  it('un motivo urgente suma sobre uno que no lo es', () => {
    const urgente = fila({ escalada_en: hace(2), motivo_escalamiento: 'tres_fallos_seguidos' });
    const normal = fila({ escalada_en: hace(2), motivo_escalamiento: 'consulta_general' });
    expect(peso(urgente) - peso(normal)).toBeCloseTo(2, 5);
  });
});

describe('los otros tres modos de orden', () => {
  it('«actividad» no antepone lo pendiente: el último mensaje manda', () => {
    // Es lo que hace útil la pestaña «Todas» para vigilar.
    const viejaPendiente = fila({
      id: 'vieja-pendiente',
      banda: BANDA.SIN_ASIGNAR,
      esperando_desde: hace(40),
      ultimo_mensaje_en: hace(40)
    });
    const recienteResuelta = fila({
      id: 'reciente-resuelta',
      estado: 'cerrada',
      ultimo_mensaje_en: hace(0)
    });
    expect(ids(ordenar([viejaPendiente, recienteResuelta], 'actividad'))).toEqual([
      'reciente-resuelta', 'vieja-pendiente'
    ]);
  });

  it('«actividad» cae a actualizado_en si no hay último mensaje', () => {
    const sinMensaje = fila({ id: 'sin', ultimo_mensaje_en: null, actualizado_en: hace(0) });
    const conMensaje = fila({ id: 'con', ultimo_mensaje_en: hace(5) });
    expect(ids(ordenar([conMensaje, sinMensaje], 'actividad'))).toEqual(['sin', 'con']);
  });

  it('«creacion» ordena por actualizado_en descendente, sin mirar nada más', () => {
    const a = fila({ id: 'nueva', actualizado_en: hace(1), banda: BANDA.LEGADO });
    const b = fila({ id: 'vieja', actualizado_en: hace(9), banda: BANDA.CLIENTE_ESPERA });
    expect(ids(ordenar([b, a], 'creacion'))).toEqual(['nueva', 'vieja']);
  });

  it('«espera» es el orden CRUDO por escalada_en, sin bandas ni ponderación', () => {
    // Existe para poder comprobar el otro: si «Recomendado» pone algo arriba
    // que no lleva la espera más larga, acá se ve por qué.
    const mejorBanda = fila({
      id: 'banda-buena',
      banda: BANDA.CLIENTE_ESPERA,
      escalada_en: hace(1),
      esperando_desde: hace(1)
    });
    const masEspera = fila({
      id: 'mas-espera',
      banda: BANDA.LEGADO,
      escalada_en: hace(30),
      esperando_desde: hace(30)
    });
    expect(ids(ordenar([mejorBanda, masEspera], 'espera'))).toEqual([
      'mas-espera', 'banda-buena'
    ]);
    // Y con «recomendado» sobre las mismas dos, gana la banda. Las dos vistas
    // discrepan a propósito.
    expect(ids(ordenar([mejorBanda, masEspera], 'recomendado'))).toEqual([
      'banda-buena', 'mas-espera'
    ]);
  });
});

describe('ordenar no muta la lista que recibe', () => {
  it('devuelve una copia', () => {
    const entrada = [
      fila({ id: 'b', banda: BANDA.LEGADO, esperando_desde: hace(1) }),
      fila({ id: 'a', banda: BANDA.CLIENTE_ESPERA, esperando_desde: hace(1) })
    ];
    const salida = ordenar(entrada, 'recomendado');
    expect(ids(entrada)).toEqual(['b', 'a']);
    expect(ids(salida)).toEqual(['a', 'b']);
    expect(salida).not.toBe(entrada);
  });
});
