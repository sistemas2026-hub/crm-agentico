import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * LAS INSIGNIAS DE TRABAJO HUMANO Y «DEXTER RESOLVIÓ HOY»  --  12/11/2026
 *
 * Atraviesa `insigniasDeTrabajo` y `resolucionDelDia` con los lectores de cada
 * módulo sustituidos y el `fetch` al motor doblado. Se afirma sobre lo que
 * recibe el layout: qué claves llegan, cuáles no, y cuántas veces se le pidió
 * algo al motor.
 */
const f = vi.hoisted(() => ({
  destino: /** @type {any} */ (null),
  solicitudes: /** @type {any} */ ({ solicitudes: [] }),
  bloqueos: /** @type {any} */ ({ datos: { bloqueos: [] }, error: null }),
  pedidosBloqueos: 0
}));
vi.mock('$env/dynamic/private', () => ({ env: {} }));
vi.mock('$lib/server/v2/tenant.js', () => ({ destinoDelAsistente: async () => f.destino }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));
vi.mock('$lib/server/v2/today.js', () => ({ getToday: async () => null }));
vi.mock('$lib/server/v2/solicitudes.js', () => ({ leerBandeja: async () => f.solicitudes }));
vi.mock('$lib/server/v2/programacion-noc.js', () => ({
  leerBloqueosAbiertos: async () => {
    f.pedidosBloqueos += 1;
    return f.bloqueos;
  }
}));
vi.mock('$lib/server/v2/inventario.js', () => ({ leerReporte: async () => ({ filas: [] }) }));

const { insigniasDeTrabajo, olvidarInsignias, resolucionDelDia, olvidarResolucion, INSIGNIAS_FRESCAS_MS } =
  await import('./hoy-operacion.js');

/** @param {(url: string) => any} responder @param {string} [rol] @param {string} [org] */
function evento(responder, rol = 'ADMIN', org = 'org-a') {
  const pedidas = /** @type {string[]} */ ([]);
  return {
    pedidas,
    ev: /** @type {any} */ ({
      cookies: { get: () => undefined },
      locals: { org: { id: org }, profile: { role: rol } },
      fetch: async (/** @type {string} */ url) => {
        pedidas.push(String(url));
        const r = responder(String(url));
        if (r instanceof Error) throw r;
        return { ok: true, status: 200, json: async () => r };
      }
    })
  };
}

const cola = { conversaciones: [{ banda: 1 }, { banda: 2 }, { banda: 3 }, { banda: 4 }, { banda: null }] };

beforeEach(() => {
  olvidarInsignias();
  olvidarResolucion();
  f.destino = { baseUrl: 'http://motor', tenant: 'demo' };
  f.solicitudes = { solicitudes: [{}, {}] };
  f.bloqueos = { datos: { bloqueos: [{ requiere_noc: true }, { requiere_noc: false }] }, error: null };
  f.pedidosBloqueos = 0;
});

describe('insignias del menú', () => {
  it('cuentan lo mismo que «Por área»: bandas 1-3, bloqueos del NOC, solicitudes', async () => {
    const { ev } = evento(() => cola);
    expect(await insigniasDeTrabajo(ev)).toEqual({ conversaciones: 3, supervisor: 1, instalaciones: 2 });
  });

  it('EL EFECTO: con el motor caído no hay insignia de conversaciones (ni un 0)', async () => {
    const { ev } = evento(() => new Error('ECONNREFUSED'));
    const n = await insigniasDeTrabajo(ev);
    expect(n).not.toHaveProperty('conversaciones');
    expect(n).toEqual({ supervisor: 1, instalaciones: 2 });
  });

  it('una fuente que contesta con error tampoco tiene insignia', async () => {
    f.solicitudes = { solicitudes: [], error: 'Sin permiso' };
    f.bloqueos = { datos: null, error: 'Sin permiso' };
    const { ev } = evento(() => cola);
    expect(await insigniasDeTrabajo(ev)).toEqual({ conversaciones: 3 });
  });

  it('a un USER no se le piden los bloqueos ni le llega la insignia del Supervisor', async () => {
    const { ev } = evento(() => cola, 'USER');
    const n = await insigniasDeTrabajo(ev);
    expect(n).not.toHaveProperty('supervisor');
    expect(f.pedidosBloqueos).toBe(0);
  });

  it('no es una ida al motor por clic: se recuerda por organización y rol', async () => {
    const a = evento(() => cola);
    await insigniasDeTrabajo(a.ev);
    await insigniasDeTrabajo(a.ev);
    await insigniasDeTrabajo(a.ev);
    expect(a.pedidas.length).toBe(1);
    // Otra empresa no ve lo recordado de la primera: pregunta la suya.
    const b = evento(() => ({ conversaciones: [] }), 'ADMIN', 'org-b');
    expect(await insigniasDeTrabajo(b.ev)).toMatchObject({ conversaciones: 0 });
    expect(b.pedidas.length).toBe(1);
  });

  it('vencida, muestra la última mientras renueva por detrás', async () => {
    vi.useFakeTimers();
    try {
      const a = evento(() => cola);
      await insigniasDeTrabajo(a.ev);
      vi.advanceTimersByTime(INSIGNIAS_FRESCAS_MS + 1000);
      const b = evento(() => ({ conversaciones: [] }));
      // Contesta al instante con lo de antes...
      expect(await insigniasDeTrabajo(b.ev)).toMatchObject({ conversaciones: 3 });
      await vi.runAllTimersAsync();
      // ...y la siguiente ya trae lo renovado.
      expect(await insigniasDeTrabajo(b.ev)).toMatchObject({ conversaciones: 0 });
      expect(b.pedidas.length).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('sin organización no hay insignias ni pedidos', async () => {
    const { ev, pedidas } = evento(() => cola);
    ev.locals.org = null;
    expect(await insigniasDeTrabajo(ev)).toEqual({});
    expect(pedidas).toEqual([]);
  });
});

describe('«Dexter resolvió hoy»', () => {
  const tablero = {
    resolucion_sin_persona: { tasa: 0.8, resueltas: 40, cerradas: 50 },
    recontacto: { tasa: 0.1, evaluadas: 30, ventana_horas: 72 },
    satisfaccion: { promedio: 4.5, respondidas: 12 }
  };

  it('la palanca llega con sus dos contrapesos, de las últimas 24 h', async () => {
    const { ev, pedidas } = evento(() => tablero);
    expect(await resolucionDelDia(ev)).toEqual({
      resueltas: 40,
      cerradas: 50,
      tasa: 0.8,
      recontacto: { tasa: 0.1, evaluadas: 30, ventana_horas: 72 },
      satisfaccion: { promedio: 4.5, respondidas: 12 }
    });
    expect(pedidas[0]).toContain('/reportes/capacidad?');
    expect(pedidas[0]).toContain('dias=1');
  });

  it('sin un contrapeso no hay tarjeta: la resolución sola no se muestra', async () => {
    const { ev } = evento(() => ({ ...tablero, satisfaccion: undefined }));
    expect(await resolucionDelDia(ev)).toBeNull();
  });

  it('con el motor caído es null, no rechaza', async () => {
    const { ev } = evento(() => new Error('caído'));
    await expect(resolucionDelDia(ev)).resolves.toBeNull();
  });
});
