import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/server/v2/tenant.js', () => ({
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'rapilink' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));

const { load, actions } = await import('./+page.server.js');
/** @param {any} e */
const cargar = async (e) => /** @type {any} */ (await load(e));

/**
 * El tablero de capacidad (30/10/2026, PRD §2 y §8.17 Ola 1).
 *
 * Lo que se protege es la CADENA, no el cálculo (ese está probado contra
 * PostgreSQL en tests/test_tablero_capacidad_base.py): que cada clave que
 * escribe el motor llegue a la pantalla con el MISMO nombre. CLAUDE.md §6: el
 * 29/09/2026 `requiere_noc` viajaba bien desde el backend y la capa servidor
 * del frontend lo dejaba caer, con todas las pruebas de backend en verde.
 */

// La forma EXACTA que devuelve GET /reportes/capacidad
// (nucleo/observabilidad/capacidad.py::componer), copiada de una corrida real.
const DEL_MOTOR = {
  dias: 30,
  desde: '2026-09-30T00:00:00+00:00',
  hasta: '2026-10-30T00:00:00+00:00',
  canales: ['whatsapp'],
  casos_por_persona: { valor: 4.0, casos: 8, personas: 2 },
  resolucion_sin_persona: { tasa: 0.375, resueltas: 3, cerradas: 8 },
  recontacto: { ventana_horas: 72, tasa: 0.125, tasa_sin_persona: 0.3333,
                recontactos: 1, recontactos_sin_persona: 1 },
  satisfaccion: { promedio: 4.0, respondidas: 2, enviadas: 3 },
  visitas_evitadas: { valor: 1, reinicios_confirmados: 2, dias_sin_visita: 7,
                      definicion: 'accion remota confirmada sin visita...' },
  minutos_ahorrados: { total: null, por_conversaciones: null, por_visitas: null,
                       motivo: 'la empresa no declaro: minutos por conversacion, minutos por visita' },
  tiempo_hasta_resolucion: { mediana_minutos: 45.0 }
};

// La forma EXACTA de GET /reportes/autonomia-ganada (nucleo/seguridad/autonomia_ganada.py).
const AUTONOMIA = {
  piso: { minimo_revisadas: 20, ventana_dias: 14, tasa_minima_aprobacion: 0.9 },
  acciones: [
    { accion: 'reiniciar_ont', candidata: true, no_candidata: [], elegible: false, tasa_aprobacion: 1.0,
      umbrales: { minimo_revisadas: 30, ventana_dias: 30, tasa_minima_aprobacion: 0.95 },
      evidencia: { revisadas: 12, rechazadas: 0, fallidas: 0, confirmadas: 9, no_confirmadas: 0,
                   no_verificables: 1, pendientes: 2 },
      desde: '2026-10-01T00:00:00+00:00',
      faltan: [{ condicion: 'minimo_revisadas', tiene: 12, necesita: 30 }] },
    { accion: 'registrar_pago', candidata: false, no_candidata: ['efecto_no_verificable', 'sin_previas_en_codigo'],
      elegible: false }
  ]
};

const SEIS = ['casos_por_persona', 'resolucion_sin_persona', 'recontacto', 'satisfaccion',
  'visitas_evitadas', 'minutos_ahorrados', 'tiempo_hasta_resolucion'];

/** @param {{ rol?: string, dias?: number }} [o] */
function evento({ rol = 'ADMIN', dias } = {}) {
  const url = new URL('http://crm/capacidad' + (dias ? `?dias=${dias}` : ''));
  return /** @type {any} */ ({ locals: { profile: { role: rol } }, url, fetch: globalThis.fetch });
}

describe('el tablero de capacidad, de la respuesta del motor a la pantalla', () => {
  /** @type {any} */
  let pedido;
  beforeEach(() => {
    pedido = null;
    globalThis.fetch = /** @type {any} */ (vi.fn(async (url) => {
      if (String(url).includes('/reportes/autonomia-ganada')) {
        return { ok: true, status: 200, json: async () => structuredClone(AUTONOMIA) };
      }
      pedido = String(url);
      return { ok: true, status: 200, json: async () => structuredClone(DEL_MOTOR) };
    }));
  });

  it('cada una de las métricas llega con el nombre y el valor que escribe el motor', async () => {
    const data = await cargar(evento());
    for (const clave of SEIS) {
      expect(data.tablero[clave], clave).toEqual(DEL_MOTOR[clave]);
    }
  });

  it('un null del motor llega como null, con su motivo: no se convierte en 0', async () => {
    const data = await cargar(evento());
    expect(data.tablero.minutos_ahorrados.total).toBeNull();
    expect(data.tablero.minutos_ahorrados.motivo).toContain('no declaro');
  });

  it('pide el período elegido y para la empresa de la sesión', async () => {
    await cargar(evento({ dias: 7 }));
    expect(pedido).toContain('/reportes/capacidad?');
    expect(pedido).toContain('tenant=rapilink');
    expect(pedido).toContain('dias=7');
  });

  it('un período que no está en la lista vuelve a 30 días', async () => {
    const data = await cargar(evento({ dias: 5000 }));
    expect(data.dias).toBe(30);
    expect(pedido).toContain('dias=30');
  });

  it('si el motor falla, la pantalla lo dice y no inventa un tablero', async () => {
    globalThis.fetch = /** @type {any} */ (vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ error: 'No se pudo calcular el tablero.' })
    })));
    const data = await cargar(evento());
    expect(data.tablero).toBeNull();
    expect(data.error).toBeTruthy();
  });

  it('solo ADMIN: son cifras de negocio de la empresa', async () => {
    await expect(cargar(evento({ rol: 'USER' }))).rejects.toMatchObject({ status: 303 });
  });
});

/** @param {Record<string, string>} campos @param {string} [rol] */
function envio(campos, rol = 'ADMIN') {
  const f = new FormData();
  for (const [k, v] of Object.entries(campos)) f.set(k, v);
  return /** @type {any} */ ({ locals: { profile: { role: rol } }, request: { formData: async () => f },
                               fetch: globalThis.fetch });
}

describe('lo que declara la empresa: minutos y personas del equipo (§3.3)', () => {
  /** @type {any} */
  let cuerpo;
  beforeEach(() => {
    cuerpo = null;
    globalThis.fetch = /** @type {any} */ (vi.fn(async (url, opciones) => {
      cuerpo = { url: String(url), metodo: opciones?.method, datos: JSON.parse(opciones?.body || '{}') };
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    }));
  });

  it('manda los tres números al motor, para la empresa de la sesión', async () => {
    await actions.declarar(envio({ minutos_por_conversacion: '12', minutos_por_visita: '90',
                                   personas_del_equipo: '4' }));
    expect(cuerpo.url).toContain('/configuracion/capacidad');
    expect(cuerpo.metodo).toBe('PUT');
    expect(cuerpo.datos).toEqual({ tenant: 'rapilink', minutos_por_conversacion: 12,
                                   minutos_por_visita: 90, personas_del_equipo: 4 });
  });

  it('un campo vacío se manda como null: "sin declarar", nunca un 0', async () => {
    await actions.declarar(envio({ minutos_por_conversacion: '', minutos_por_visita: '90',
                                   personas_del_equipo: '' }));
    expect(cuerpo.datos.minutos_por_conversacion).toBeNull();
    expect(cuerpo.datos.personas_del_equipo).toBeNull();
  });

  it('un número que no es entero positivo no viaja', async () => {
    const r = /** @type {any} */ (await actions.declarar(envio({ minutos_por_conversacion: '-3',
      minutos_por_visita: '', personas_del_equipo: '' })));
    expect(r.status).toBe(400);
    expect(cuerpo).toBeNull();
  });

  it('solo ADMIN', async () => {
    const r = /** @type {any} */ (await actions.declarar(envio({ minutos_por_conversacion: '12',
      minutos_por_visita: '', personas_del_equipo: '' }, 'USER')));
    expect(r.status).toBe(403);
    expect(cuerpo).toBeNull();
  });
});

describe('la autonomía ganada, de la respuesta del motor a la pantalla', () => {
  beforeEach(() => {
    globalThis.fetch = /** @type {any} */ (vi.fn(async (url) => {
      if (String(url).includes('/reportes/autonomia-ganada')) {
        expect(String(url)).toContain('tenant=rapilink');
        return { ok: true, status: 200, json: async () => structuredClone(AUTONOMIA) };
      }
      return { ok: true, status: 200, json: async () => structuredClone(DEL_MOTOR) };
    }));
  });

  it('llega entera y con los mismos nombres', async () => {
    const d = await cargar(evento());
    expect(d.autonomia).toEqual(AUTONOMIA);
    expect(d.errorAutonomia).toBeNull();
  });

  it('si el motor no la calcula, el tablero se muestra igual', async () => {
    globalThis.fetch = /** @type {any} */ (vi.fn(async (url) =>
      String(url).includes('/reportes/autonomia-ganada')
        ? { ok: false, status: 500, json: async () => ({ error: 'No se pudo calcular la autonomia ganada.' }) }
        : { ok: true, status: 200, json: async () => structuredClone(DEL_MOTOR) }));
    const d = await cargar(evento());
    expect(d.tablero).toEqual(DEL_MOTOR);
    expect(d.autonomia).toBeNull();
    expect(d.errorAutonomia).toMatch(/autonomia ganada/);
  });
});
