import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/server/v2/tenant.js', () => ({
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'rapilink' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({}) }));

const { load } = await import('./+page.server.js');
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
