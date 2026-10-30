import { describe, it, expect } from 'vitest';
import { frescura, estadoVisible, UMBRALES } from './frescura.js';

/**
 * Lo que se fija acá es que la pantalla NO afirme frescura que no tiene.
 *
 * El error que esto evita es silencioso por definición: un agente quieto
 * porque no tiene trabajo y uno quieto porque su backend murió se ven igual,
 * y el segundo caso es justo cuando alguien necesita enterarse.
 */

const T = 1_700_000_000_000;      // un «ahora» fijo
const s = (n) => n * 1000;

describe('arranque: todavía no sabemos nada', () => {
  it('sin ninguna lectura NO es reposo, es sin información', () => {
    // La pantalla no nace diciendo que todo está tranquilo.
    const v = frescura({ ultimaRespuestaOk: null, ahora: T });
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('sin_lectura');
    expect(estadoVisible(null, v).estado).toBe('sin_informacion');
  });
});

describe('silencio: el backend dejó de responder', () => {
  it('pasado el umbral, deja de ser confiable', () => {
    const v = frescura({ ultimaRespuestaOk: T - s(45), ahora: T });
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('silencio');
    expect(v.detalle).toContain('45s');
  });

  it('un sondeo perdido NO dispara la alarma', () => {
    // Uno perdido es ruido; tres son un silencio. Si avisara al primero, el
    // aviso aparecería a diario y se aprendería a ignorarlo.
    const v = frescura({ ultimaRespuestaOk: T - s(13), ahora: T });
    expect(v.confiable).toBe(true);
  });

  it('justo en el umbral ya avisa', () => {
    const v = frescura({ ultimaRespuestaOk: T - s(UMBRALES.silencio_s), ahora: T });
    expect(v.confiable).toBe(false);
  });

  it('lo detecta el CLIENTE, sin que el backend diga nada', () => {
    // Es la razón de ser del módulo: si el backend no contesta, no manda un
    // aviso de que no contesta. `retraso_s` no llega.
    const v = frescura({ ultimaRespuestaOk: T - s(60), retraso_s: null, ahora: T });
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('silencio');
  });
});

describe('errores HTTP', () => {
  it('si lo ÚLTIMO fue un fallo, no se confía', () => {
    const v = frescura({ ultimaRespuestaOk: T - s(5), ultimoFallo: T - s(1), ahora: T });
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('error');
  });

  it('pero si después del fallo hubo una respuesta buena, se recupera', () => {
    // Recuperación tras pérdida de conexión: un error viejo no condena para
    // siempre, o la pantalla se quedaría en rojo tras un parpadeo.
    const v = frescura({ ultimaRespuestaOk: T - s(1), ultimoFallo: T - s(5), ahora: T });
    expect(v.confiable).toBe(true);
    expect(v.motivo).toBe('al_dia');
  });
});

describe('retraso declarado por el backend', () => {
  it('un flujo muy atrasado no es frescura, aunque la respuesta llegue', () => {
    // Una transacción en vuelo retiene el cursor. La respuesta llega al día,
    // pero los eventos que trae son viejos.
    const v = frescura({ ultimaRespuestaOk: T, retraso_s: 45, ahora: T });
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('retraso');
    expect(v.detalle).toContain('45s');
  });

  it('un retraso pequeño es normal y no asusta', () => {
    const v = frescura({ ultimaRespuestaOk: T, retraso_s: 0.4, ahora: T });
    expect(v.confiable).toBe(true);
  });

  it('retraso ausente (el backend no lo pudo medir) no invalida por sí solo', () => {
    // `_retraso_del_flujo` devuelve null si no hay permiso sobre
    // pg_stat_activity. Eso no es motivo para declarar la pantalla rota.
    const v = frescura({ ultimaRespuestaOk: T, retraso_s: null, ahora: T });
    expect(v.confiable).toBe(true);
  });
});

describe('ausencia de actividad con conexión sana', () => {
  it('eso SÍ es reposo', () => {
    const v = frescura({ ultimaRespuestaOk: T - s(2), retraso_s: 0.2, ahora: T });
    const e = estadoVisible(null, v);
    expect(e.estado).toBe('reposo');
    expect(e.procedencia).toBe('ambiente');
  });

  it('y reposo NO se llama «disponible»', () => {
    // Que no haya actividad vigente no prueba que el agente pueda atender
    // algo. Esta pantalla no responde esa pregunta.
    const e = estadoVisible(null, frescura({ ultimaRespuestaOk: T, ahora: T }));
    expect(e.estado).toBe('reposo');
    expect(JSON.stringify(e)).not.toContain('disponible');
  });
});

describe('«sin información» PREVALECE sobre todo lo demás', () => {
  const actividad = { tipo: 'consulta', etiqueta: 'consultar_olt',
                      procedencia: 'evento:3f1a2b4c-0000-4000-8000-000000000001' };

  it('una actividad vigente NO tapa un backend caído', () => {
    // Mostrar actividad vieja como si fuera actual es peor que no mostrar
    // nada: lo segundo se nota, lo primero no.
    const v = frescura({ ultimaRespuestaOk: T - s(90), ahora: T });
    const e = estadoVisible(actividad, v);
    expect(e.estado).toBe('sin_informacion');
    expect(e.estado).not.toBe('actividad');
  });

  it('con datos frescos, la actividad sí se muestra y conserva su procedencia', () => {
    const v = frescura({ ultimaRespuestaOk: T, retraso_s: 0.3, ahora: T });
    const e = estadoVisible(actividad, v);
    expect(e.estado).toBe('actividad');
    expect(e.procedencia).toMatch(/^evento:/);
  });

  it('«sin información» nunca lleva procedencia de evento', () => {
    // No saber no es una actividad operativa y no puede acabar en el
    // historial como si lo fuera.
    const e = estadoVisible(actividad, frescura({ ultimaRespuestaOk: null, ahora: T }));
    expect(e.procedencia).toBe('ambiente');
  });
});

describe('los umbrales son configurables, no constantes escondidas', () => {
  it('se pueden ajustar por empresa sin tocar el código', () => {
    const v = frescura({ ultimaRespuestaOk: T - s(20), ahora: T,
                         umbrales: { silencio_s: 10, retraso_s: 30 } });
    expect(v.confiable).toBe(false);
  });

  it('y los de por defecto están declarados en un solo sitio', () => {
    expect(UMBRALES.silencio_s).toBeGreaterThan(0);
    expect(UMBRALES.retraso_s).toBeGreaterThan(0);
  });
});
