import { describe, it, expect } from 'vitest';
import { ANIMACION_POR_TIPO, esReal, esSimulado, visualizar } from './adaptador';
import { frescura } from '../frescura.js';
import { proyectar } from '../proyeccion.js';

/**
 * LA FRONTERA ES EL SITIO DONDE SE PUEDE MENTIR SIN QUERER.
 *
 * De un lado hay instrucciones con procedencia y un veredicto; del otro, cinco
 * animaciones. Las dos equivocaciones que importan son: mostrar actividad vieja
 * como actual cuando el flujo está caído, y dejar que un movimiento de prueba
 * salga con procedencia de hecho real.
 */

const T = 1_700_000_000_000;
const uuid = (n) => `3f1a2b4c-0000-4000-8000-00000000000${n}`;
const alDia = frescura({ ultimaRespuestaOk: T, retraso_s: 0.2, ahora: T });
const caido = frescura({ ultimaRespuestaOk: T - 90_000, ahora: T });

function instruccion(tipo, { id = uuid(1), agente = 'supervisor_noc', etiqueta = 'x', caduca = T + 1000 } = {}) {
  return { id, agente, tipo, etiqueta, procedencia: `evento:${id}`, caduca_en: caduca };
}

describe('«sin información» gana siempre', () => {
  it('una actividad vigente NO tapa un motor caído', () => {
    const { estados } = visualizar([instruccion('consulta')], ['supervisor_noc'], caido, T);
    expect(estados[0].animacion).toBe('incognito');
    expect(estados[0].confiable).toBe(false);
  });

  it('con el motor caído, el rótulo de la actividad NO viaja', () => {
    // Repetir en qué andaba hace media hora es afirmar que sigue en eso.
    const { estados } = visualizar(
      [instruccion('consulta', { etiqueta: 'consultar_estado_enlace' })],
      ['supervisor_noc'],
      caido,
      T
    );
    expect(estados[0].rotulo).toBeNull();
    expect(JSON.stringify(estados[0])).not.toContain('consultar_estado_enlace');
  });

  it('sin veredicto se asume lo peor', () => {
    // No saber si los datos son de fiar es un caso de no saber.
    const { estados } = visualizar([instruccion('consulta')], ['supervisor_noc'], null, T);
    expect(estados[0].animacion).toBe('incognito');
  });

  it('«sin información» nunca lleva procedencia de hecho', () => {
    const { estados } = visualizar([instruccion('accion')], ['supervisor_noc'], caido, T);
    expect(estados[0].procedencia).toBe('ambiente');
    expect(esReal(estados[0].procedencia)).toBe(false);
  });
});

describe('cada tipo tiene su animación, y ninguna se inventa', () => {
  it('los cinco tipos del proyector están cubiertos', () => {
    for (const tipo of ['consulta', 'accion', 'falla', 'expediente', 'escalada']) {
      const { estados } = visualizar([instruccion(tipo)], ['supervisor_noc'], alDia, T);
      expect(estados[0].animacion).toBe(ANIMACION_POR_TIPO[tipo]);
    }
  });

  it('derivar y escalar comparten animación a propósito', () => {
    // Son lo mismo visto desde el puesto: algo sale de acá. Inventarles dos
    // animaciones agregaría una diferencia que el dato no sostiene.
    expect(ANIMACION_POR_TIPO.expediente).toBe(ANIMACION_POR_TIPO.escalada);
  });

  it('un tipo que la escena no sabe dibujar se CUENTA, no se disfraza', () => {
    const { estados, sinRepresentacion } = visualizar(
      [instruccion('cosa_nueva_del_futuro')],
      ['supervisor_noc'],
      alDia,
      T
    );
    expect(sinRepresentacion).toBe(1);
    expect(estados[0].animacion).toBe('incognito');
    expect(estados[0].motivo).toBe('sin_representacion');
    // Y el dato NO se pierde: la ficha puede decirlo.
    expect(estados[0].rotulo).toBe('x');
  });
});

describe('reposo', () => {
  it('sin actividad y con datos frescos, es reposo', () => {
    const { estados } = visualizar([], ['supervisor_noc'], alDia, T);
    expect(estados[0].animacion).toBe('reposo');
    expect(estados[0].confiable).toBe(true);
  });

  it('y reposo NO se llama «disponible»', () => {
    // Que no haya actividad vigente no prueba que el agente pueda atender algo.
    const { estados } = visualizar([], ['supervisor_noc'], alDia, T);
    expect(JSON.stringify(estados)).not.toContain('disponible');
  });

  it('una instrucción caducada ya no es actividad', () => {
    // Es lo que hace que el personaje vuelva solo a reposo sin que nadie tenga
    // que acordarse de apagarlo.
    const vieja = instruccion('consulta', { caduca: T - 1 });
    const { estados } = visualizar([vieja], ['supervisor_noc'], alDia, T);
    expect(estados[0].animacion).toBe('reposo');
  });
});

describe('lo simulado no se puede hacer pasar por real', () => {
  it('un lote simulado conserva su procedencia a través de la frontera', () => {
    const eventos = [{ id: uuid(7), agente: 'supervisor_noc', tipo: 'consulta', herramienta: 'x' }];
    const p = proyectar(eventos, { agentes: ['supervisor_noc'], ahora: T, simulado: true });
    const { estados } = visualizar(p.instrucciones, ['supervisor_noc'], alDia, T);
    expect(estados[0].procedencia).toBe('simulado');
    expect(esSimulado(estados[0].procedencia)).toBe(true);
    expect(esReal(estados[0].procedencia)).toBe(false);
  });

  it('y un uuid válido no lo convierte en real', () => {
    // Lo que decide no es la forma del identificador: es de qué lote viene.
    const eventos = [{ id: uuid(8), agente: 'supervisor_noc', tipo: 'accion', herramienta: 'y' }];
    const simulado = proyectar(eventos, { agentes: ['supervisor_noc'], ahora: T, simulado: true });
    const real = proyectar(eventos, { agentes: ['supervisor_noc'], ahora: T });
    expect(simulado.instrucciones[0].id).toBe(real.instrucciones[0].id);
    expect(simulado.instrucciones[0].procedencia).not.toBe(real.instrucciones[0].procedencia);
  });

  it('`esReal` exige el prefijo completo', () => {
    expect(esReal('evento:abc')).toBe(true);
    expect(esReal('evento')).toBe(false);
    expect(esReal('simulado')).toBe(false);
    expect(esReal('ambiente')).toBe(false);
    expect(esReal(null)).toBe(false);
    expect(esReal(undefined)).toBe(false);
  });
});

describe('solo se dibuja a quien tiene puesto', () => {
  it('un agente que no está en la lista no produce estado', () => {
    const { estados } = visualizar([instruccion('consulta', { agente: 'otro' })], ['supervisor_noc'], alDia, T);
    expect(estados).toHaveLength(1);
    expect(estados[0].agente).toBe('supervisor_noc');
    expect(estados[0].animacion).toBe('reposo');
  });

  it('sin agentes con puesto no hay estados, y no falla', () => {
    expect(visualizar([instruccion('consulta')], [], alDia, T).estados).toEqual([]);
  });

  it('entradas basura no tumban la frontera', () => {
    const { estados } = visualizar(null, ['supervisor_noc'], alDia, T);
    expect(estados[0].animacion).toBe('reposo');
  });
});

describe('la más reciente gana', () => {
  it('con dos instrucciones vigentes se muestra la última', () => {
    const vieja = instruccion('consulta', { id: uuid(2), caduca: T + 500 });
    const nueva = instruccion('falla', { id: uuid(3), caduca: T + 1500 });
    const { estados } = visualizar([vieja, nueva], ['supervisor_noc'], alDia, T);
    expect(estados[0].animacion).toBe('alerta');
  });
});
