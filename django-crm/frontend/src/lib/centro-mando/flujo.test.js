import { describe, it, expect, vi } from 'vitest';
import { crearFlujo } from './flujo.js';
import { frescura } from './frescura.js';

/**
 * EL TRANSPORTE Y LAS SEÑALES.
 *
 * Dos clases de afirmación acá. Las del transporte —no solapar, no consultar con
 * la pestaña oculta, no avanzar el cursor ante un fallo— y las de las señales,
 * que son las que alimentan el indicador de «sin información».
 *
 * La que más vale es la última: que el silencio se detecte SIN que el motor
 * diga nada. Es la corrección que ordenó este diseño — si el motor deja de
 * responder, no llega un retraso grande: no llega nada.
 */

const T = 1_700_000_000_000;

function respuesta(cuerpo, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    text: async () => (typeof cuerpo === 'string' ? cuerpo : JSON.stringify(cuerpo))
  };
}

const uuid = (n) => `3f1a2b4c-0000-4000-8000-0000000000${String(n).padStart(2, '0')}`;

describe('el cursor', () => {
  it('la primera consulta va sin cursor', async () => {
    const traer = vi.fn(async () => respuesta({ eventos: [], siguiente: '100.abc' }));
    const f = crearFlujo({ fetch: traer, visible: () => true });
    f.refrescar();
    await vi.waitFor(() => expect(traer).toHaveBeenCalled());
    expect(traer.mock.calls[0][0]).not.toContain('desde=');
  });

  it('la siguiente lleva el cursor que devolvió el motor', async () => {
    const traer = vi.fn(async () => respuesta({ eventos: [], siguiente: '100.abc' }));
    const f = crearFlujo({ fetch: traer, visible: () => true });
    f.refrescar();
    await vi.waitFor(() => expect(f.diagnostico().cursor).toBe('100.abc'));
    f.refrescar();
    await vi.waitFor(() => expect(traer).toHaveBeenCalledTimes(2));
    expect(traer.mock.calls[1][0]).toContain('desde=100.abc');
  });

  it('ante un fallo el cursor NO avanza', async () => {
    // Avanzarlo sería saltarse los eventos que esa consulta no trajo.
    let primera = true;
    const traer = vi.fn(async () => {
      if (primera) {
        primera = false;
        return respuesta({ eventos: [], siguiente: '100.abc' });
      }
      return respuesta({ error: 'caido' }, { ok: false, status: 502 });
    });
    const f = crearFlujo({ fetch: traer, visible: () => true });
    f.refrescar();
    await vi.waitFor(() => expect(f.diagnostico().cursor).toBe('100.abc'));
    f.refrescar();
    await vi.waitFor(() => expect(f.diagnostico().ultimoError).toBeTruthy());
    expect(f.diagnostico().cursor).toBe('100.abc');
  });

  it('un salto del motor se cuenta y no se silencia', async () => {
    const traer = async () => respuesta({ eventos: [], siguiente: '9.x', salto: true });
    const f = crearFlujo({ fetch: traer, visible: () => true });
    f.refrescar();
    await vi.waitFor(() => expect(f.diagnostico().saltos).toBe(1));
  });
});

describe('las reglas del transporte', () => {
  it('con la pestaña oculta no consulta', async () => {
    const traer = vi.fn(async () => respuesta({ eventos: [] }));
    const f = crearFlujo({ fetch: traer, visible: () => false });
    f.refrescar();
    await Promise.resolve();
    expect(traer).not.toHaveBeenCalled();
  });

  it('y lo dice, en vez de dejar crecer el silencio en silencio', async () => {
    // Si no lo dijera, la pantalla acusaría al motor de algo que hizo ella.
    const f = crearFlujo({ fetch: async () => respuesta({ eventos: [] }), visible: () => false });
    f.refrescar();
    await Promise.resolve();
    expect(f.senales().pausado).toBe(true);
  });

  it('no solapa: si la anterior no volvió, la siguiente no sale', async () => {
    // Con la base lenta, disparar igual multiplica la carga justo cuando peor
    // está.
    let resolver;
    const traer = vi.fn(() => new Promise((r) => (resolver = r)));
    const f = crearFlujo({ fetch: traer, visible: () => true });
    f.refrescar();
    f.refrescar();
    f.refrescar();
    expect(traer).toHaveBeenCalledTimes(1);
    resolver(respuesta({ eventos: [] }));
  });

  it('una respuesta que no es JSON no se convierte en un error ilegible', async () => {
    // Durante un redespliegue el proxy contesta una página de error, y con la
    // sesión caducada contesta el HTML del login.
    const f = crearFlujo({
      fetch: async () => respuesta('<!doctype html><html>…', { ok: true }),
      visible: () => true
    });
    f.refrescar();
    await vi.waitFor(() => expect(f.senales().ultimoFallo).not.toBeNull());
    expect(f.diagnostico().ultimoError).toBeTruthy();
  });

  it('un 401 dice qué hacer, no qué pasó', async () => {
    const f = crearFlujo({
      fetch: async () => respuesta({ error: 'No autenticado' }, { ok: false, status: 401 }),
      visible: () => true
    });
    f.refrescar();
    await vi.waitFor(() => expect(f.diagnostico().ultimoError).toContain('Vuelve a entrar'));
  });
});

describe('las señales que alimentan el indicador', () => {
  it('antes de la primera respuesta no hay nada, y eso NO es reposo', () => {
    const f = crearFlujo({ fetch: async () => respuesta({ eventos: [] }) });
    const v = frescura(f.senales());
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('sin_lectura');
  });

  it('una respuesta buena deja el veredicto al día', async () => {
    const f = crearFlujo({
      fetch: async () => respuesta({ eventos: [], siguiente: '1.a', retraso_s: 0.3 }),
      visible: () => true
    });
    f.refrescar();
    await vi.waitFor(() => expect(f.senales().ultimaRespuestaOk).not.toBeNull());
    expect(frescura(f.senales()).motivo).toBe('al_dia');
  });

  it('el silencio se detecta SIN que el motor diga nada', async () => {
    // La afirmación central: `retraso_s` no llega cuando el motor no responde.
    let reloj = T;
    const f = crearFlujo({
      fetch: async () => respuesta({ eventos: [], siguiente: '1.a', retraso_s: 0.1 }),
      visible: () => true,
      ahora: () => reloj
    });
    f.refrescar();
    await vi.waitFor(() => expect(f.senales().ultimaRespuestaOk).toBe(T));
    reloj = T + 90_000;
    const v = frescura(f.senales());
    expect(v.confiable).toBe(false);
    expect(v.motivo).toBe('silencio');
  });

  it('el retraso declarado por el motor viaja tal cual', async () => {
    const f = crearFlujo({
      fetch: async () => respuesta({ eventos: [], siguiente: '1.a', retraso_s: 47.5 }),
      visible: () => true
    });
    f.refrescar();
    await vi.waitFor(() => expect(f.senales().retraso_s).toBe(47.5));
    expect(frescura(f.senales()).motivo).toBe('retraso');
  });

  it('un retraso que el motor no pudo medir no invalida por sí solo', async () => {
    const f = crearFlujo({
      fetch: async () => respuesta({ eventos: [], siguiente: '1.a', retraso_s: null }),
      visible: () => true
    });
    f.refrescar();
    await vi.waitFor(() => expect(f.senales().ultimaRespuestaOk).not.toBeNull());
    expect(frescura(f.senales()).confiable).toBe(true);
  });
});

describe('la proyección del lote', () => {
  it('los eventos llegan ya convertidos en instrucciones', async () => {
    const f = crearFlujo({
      fetch: async () =>
        respuesta({
          eventos: [{ id: uuid(1), agente: 'supervisor_noc', tipo: 'consulta', herramienta: 'h' }],
          siguiente: '2.b'
        }),
      visible: () => true,
      agentes: ['supervisor_noc']
    });
    const lotes = [];
    f.alLote((l) => lotes.push(l));
    f.refrescar();
    await vi.waitFor(() => expect(lotes).toHaveLength(1));
    expect(lotes[0].instrucciones).toHaveLength(1);
    expect(lotes[0].instrucciones[0].procedencia).toBe(`evento:${uuid(1)}`);
  });

  it('un evento de un agente sin puesto no produce instrucción', async () => {
    const f = crearFlujo({
      fetch: async () =>
        respuesta({
          eventos: [{ id: uuid(2), agente: 'ventas', tipo: 'consulta', herramienta: 'h' }],
          siguiente: '3.c'
        }),
      visible: () => true,
      agentes: ['supervisor_noc']
    });
    const lotes = [];
    f.alLote((l) => lotes.push(l));
    f.refrescar();
    await vi.waitFor(() => expect(lotes).toHaveLength(1));
    expect(lotes[0].instrucciones).toHaveLength(0);
    expect(lotes[0].descartados.agente_desconocido).toBe(1);
  });

  it('el flujo real NUNCA marca su lote como simulado', async () => {
    // Si lo hiciera, la actividad real se iría al historial de demostración y
    // el historial real quedaría vacío para siempre, sin un error que avisara.
    const f = crearFlujo({
      fetch: async () =>
        respuesta({
          eventos: [{ id: uuid(3), agente: 'supervisor_noc', tipo: 'accion', herramienta: 'h' }],
          siguiente: '4.d'
        }),
      visible: () => true,
      agentes: ['supervisor_noc']
    });
    const lotes = [];
    f.alLote((l) => lotes.push(l));
    f.refrescar();
    await vi.waitFor(() => expect(lotes).toHaveLength(1));
    expect(lotes[0].instrucciones[0].procedencia).not.toBe('simulado');
  });
});

describe('detener', () => {
  it('después de detener no se emite nada más', async () => {
    const f = crearFlujo({ fetch: async () => respuesta({ eventos: [] }), visible: () => true });
    const lotes = [];
    f.alLote((l) => lotes.push(l));
    f.arrancar();
    f.detener();
    f.refrescar();
    await Promise.resolve();
    expect(lotes).toHaveLength(0);
  });
});
