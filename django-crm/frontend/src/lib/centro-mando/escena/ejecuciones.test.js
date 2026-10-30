import { describe, it, expect } from 'vitest';
import { esEjecucion, esReal, esSimulado, visualizar } from './adaptador';
import { frescura } from '../frescura.js';

/**
 * EL TURNO EN CURSO, Y QUÉ GANA CUANDO HAY DOS VERDADES A LA VEZ.
 *
 * Fase 3B. Hasta ahora la oficina solo podía representar cosas que YA PASARON:
 * `tool_calls` se escribe cuando la llamada termina, así que una herramienta
 * lenta y una recién terminada se ven igual, y el motor se niega —con razón— a
 * emitir `waiting_tool`.
 *
 * Con la ejecución abierta hay un hecho que dice «esto SIGUE pasando». Lo que
 * se fija acá es el orden de precedencia, que es donde una pantalla empieza a
 * afirmar cosas sin querer:
 *
 *   1. no saber gana siempre                   (frescura)
 *   2. una ejecución vieja ES no saber         (creible: false)
 *   3. un acontecimiento gana al trabajo de fondo
 *   4. una ejecución viva sostiene el tecleo
 *   5. lo demás, como antes
 */

const T = 1_700_000_000_000;
const uuid = (n) => `3f1a2b4c-0000-4000-8000-00000000000${n}`;
const AG = 'supervisor_noc';

const alDia = frescura({ ultimaRespuestaOk: T, retraso_s: 0.2, ahora: T });
const caido = frescura({ ultimaRespuestaOk: T - 90_000, ahora: T });

const viva = { id: uuid(9), agente: AG, edad_s: 3.2, creible: true };
const vieja = { id: uuid(8), agente: AG, edad_s: 4000, creible: false };

function instruccion(tipo, { id = uuid(1), etiqueta = 'x', caduca = T + 1000 } = {}) {
  return { id, agente: AG, tipo, etiqueta, procedencia: `evento:${id}`, caduca_en: caduca };
}

describe('un turno en curso sostiene la actividad', () => {
  it('sin ningún evento, una ejecución viva ya muestra trabajo', () => {
    // Esto es lo que la fase entera compra: antes, sin eventos terminados, el
    // agente aparecía en reposo aunque estuviera a mitad de un turno.
    const { estados } = visualizar([], [AG], alDia, T, [viva]);
    expect(estados[0].animacion).toBe('teclear');
    expect(estados[0].confiable).toBe(true);
  });

  it('la animación NO caduca sola', () => {
    // Una instrucción de evento dura 900 ms y se apaga. Esta dura hasta que la
    // ejecución se cierre, que es el cambio de fondo de 3B.
    const { estados } = visualizar([], [AG], alDia, T, [viva]);
    expect(estados[0].hasta).toBeNull();
  });

  it('se puede rastrear hasta la fila que la causó', () => {
    const { estados } = visualizar([], [AG], alDia, T, [viva]);
    expect(estados[0].procedencia).toBe(`ejecucion:${uuid(9)}`);
    expect(esEjecucion(estados[0].procedencia)).toBe(true);
  });

  it('y NO se hace pasar por un hecho del historial', () => {
    // Un trabajo en curso todavía no es un hecho que contar. Si pasara por
    // `esReal` acabaría en el historial como algo que ocurrió.
    const { estados } = visualizar([], [AG], alDia, T, [viva]);
    expect(esReal(estados[0].procedencia)).toBe(false);
    expect(esSimulado(estados[0].procedencia)).toBe(false);
  });

  it('no inventa el rótulo de lo que está haciendo', () => {
    // El turno está en curso y todavía no se sabe con qué terminó. Poner el
    // nombre de lo último sería contar como presente algo que ya pasó.
    const previa = instruccion('consulta', { etiqueta: 'consultar_potencia_optica' });
    const { estados } = visualizar([previa], [AG], alDia, T, [viva]);
    expect(estados[0].rotulo).toBeNull();
    expect(JSON.stringify(estados[0])).not.toContain('consultar_potencia_optica');
  });
});

describe('una ejecución que lleva demasiado NO es trabajo', () => {
  it('es «no sé», no «trabajando»', () => {
    // Lleva abierta más de lo que un turno puede durar: no sabemos si sigue o
    // si el proceso murió a mitad. Las dos cosas se ven igual desde acá.
    const { estados } = visualizar([], [AG], alDia, T, [vieja]);
    expect(estados[0].animacion).toBe('incognito');
    expect(estados[0].confiable).toBe(false);
    expect(estados[0].motivo).toBe('ejecucion_sin_noticias');
  });

  it('y tampoco es reposo', () => {
    // Reposo afirmaría que no tiene trabajo, y lo que pasa es que no sabemos.
    const { estados } = visualizar([], [AG], alDia, T, [vieja]);
    expect(estados[0].animacion).not.toBe('reposo');
  });

  it('no lleva procedencia de ejecución: no estamos afirmando ninguna', () => {
    const { estados } = visualizar([], [AG], alDia, T, [vieja]);
    expect(estados[0].procedencia).toBe('ambiente');
  });

  it('entre dos abiertas gana la más nueva', () => {
    // Puede haber dos si un proceso murió sin cerrar la anterior. Mostrar la
    // vieja diría que lleva horas trabajando.
    const { estados } = visualizar([], [AG], alDia, T, [vieja, viva]);
    expect(estados[0].animacion).toBe('teclear');
    expect(estados[0].procedencia).toContain(uuid(9));
  });
});

describe('qué gana sobre qué', () => {
  it('«sin información» gana incluso sobre un turno en curso', () => {
    // No saber gana siempre. Con el flujo caído, la ejecución que tenemos es
    // de la última lectura buena: afirmar que sigue abierta es afirmar algo
    // que dejamos de poder ver.
    const { estados } = visualizar([], [AG], caido, T, [viva]);
    expect(estados[0].animacion).toBe('incognito');
    expect(estados[0].motivo).not.toBe('ejecucion_sin_noticias');
  });

  it('un fallo reciente gana sobre el trabajo de fondo', () => {
    // Teclear es el fondo, y el fondo no puede tapar un acontecimiento.
    const { estados } = visualizar([instruccion('falla')], [AG], alDia, T, [viva]);
    expect(estados[0].animacion).toBe('alerta');
  });

  it('una derivación y una escalada también', () => {
    for (const tipo of ['expediente', 'escalada']) {
      const { estados } = visualizar([instruccion(tipo)], [AG], alDia, T, [viva]);
      expect(estados[0].animacion, tipo).toBe('despachar');
    }
  });

  it('pero una consulta terminada NO interrumpe el turno en curso', () => {
    // Las dos dirían «teclear»; lo que cambia es que la del turno no caduca.
    // Dejar ganar a la consulta haría que el personaje se detuviera a mitad del
    // trabajo porque una de sus llamadas terminó.
    const { estados } = visualizar([instruccion('consulta')], [AG], alDia, T, [viva]);
    expect(estados[0].animacion).toBe('teclear');
    expect(estados[0].hasta).toBeNull();
    expect(esEjecucion(estados[0].procedencia)).toBe(true);
  });
});

describe('sin ejecuciones, todo sigue como antes', () => {
  it('reposo cuando no hay nada', () => {
    expect(visualizar([], [AG], alDia, T, []).estados[0].animacion).toBe('reposo');
    expect(visualizar([], [AG], alDia, T).estados[0].animacion).toBe('reposo');
  });

  it('un evento terminado sigue produciendo su destello acotado', () => {
    const { estados } = visualizar([instruccion('consulta')], [AG], alDia, T, []);
    expect(estados[0].animacion).toBe('teclear');
    expect(estados[0].hasta).toBe(T + 1000);
    expect(esReal(estados[0].procedencia)).toBe(true);
  });

  it('una ejecución de OTRO agente no anima este puesto', () => {
    const ajena = { id: uuid(7), agente: 'ventas', edad_s: 2, creible: true };
    expect(visualizar([], [AG], alDia, T, [ajena]).estados[0].animacion).toBe('reposo');
  });

  it('entradas basura no tumban la frontera', () => {
    const { estados } = visualizar([], [AG], alDia, T, [null, {}, { agente: null }]);
    expect(estados[0].animacion).toBe('reposo');
  });
});
