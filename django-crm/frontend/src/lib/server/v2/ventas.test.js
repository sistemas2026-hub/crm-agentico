/**
 * El embudo de ventas, de lo que contesta Django a lo que recibe la página
 * (12/11/2026). Se prueba el `load` de `/ventas` y de `/leads/[id]` con la
 * respuesta real de `leads/embudo.py` (forma copiada de la prueba de Django),
 * no las funciones sueltas: un salto que pierde o renombra un dato se ve acá.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

// El tipo de `load` pide el RequestEvent completo; la prueba pasa solo lo que usa.
const load = /** @type {any} */ ((await import('../../../routes/(app)/ventas/+page.server.js')).load);
const { leerSolicitudesDelLead, periodoDe } = await import('$lib/server/v2/ventas.js');

const cookies = /** @type {any} */ ({ get: () => 'token' });

const RESPUESTA = {
  etapas: ['chats', 'links', 'abiertos', 'enviadas', 'aprobadas', 'instaladas', 'activas'],
  conteos: { chats: null, links: 9, abiertos: 7, enviadas: 6, aprobadas: 3, instaladas: 1, activas: null },
  sin_dato: { chats: 'motor sin consulta', activas: 'requiere al ISP' },
  instalacion_sin_dato: 1,
  pasos: [
    { de: 'links', a: 'abiertos', tasa: 0.7778 },
    { de: 'abiertos', a: 'enviadas', tasa: 0.8571 },
    { de: 'enviadas', a: 'aprobadas', tasa: 0.5 },
    { de: 'aprobadas', a: 'instaladas', tasa: 0.3333 }
  ],
  tiempos: [{ de: 'aprobadas', a: 'instaladas', horas: 38, muestras: 1 }],
  caidas: { link_vencido_sin_enviar: 1, canceladas: { total: 1, sin_motivo: 0, motivos: [] }, sin_factibilidad: { total: 0, notas: [] } },
  detenidas: {
    sin_abrir: { total: 1, filas: [{ solicitud_id: 's1', lead_id: 'L1', nombre: 'Ana', horas: 72 }] },
    abierto_sin_enviar: { total: 1, filas: [{ solicitud_id: 's2', lead_id: null, nombre: 'Beto', horas: 48 }] },
    esperando_decision: { total: 1, filas: [{ solicitud_id: 's3', lead_id: 'L3', nombre: 'Caro', horas: 60 }] },
    aprobada_sin_instalar: {
      total: 2,
      filas: [
        { solicitud_id: 's5', nombre: 'Dani', motivo: 'orden_abierta', caso_id: 'C5', orden_numero: 2 },
        { solicitud_id: 's6', nombre: 'Eva', motivo: 'sin_ticket', caso_id: null }
      ]
    }
  }
};

/** @param {string} qs */
const evento = (qs) => /** @type {any} */ ({ cookies, url: new URL(`http://x/ventas${qs}`) });

describe('/ventas: el load', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('pide el periodo de la URL y entrega los números de Django sin recalcularlos', async () => {
    apiRequest.mockResolvedValue(RESPUESTA);
    const d = await load(evento('?dias=90'));
    expect(apiRequest.mock.calls[0][0]).toBe('/leads/embudo/?dias=90');
    const links = d.etapas.find((/** @type {any} */ e) => e.clave === 'links');
    const instaladas = d.etapas.find((/** @type {any} */ e) => e.clave === 'instaladas');
    expect(links.valor).toBe(9);
    expect(instaladas.valor).toBe(1);
    expect(instaladas.pasoDesdeAnterior).toBe(33.3);
    expect(d.instalacionSinDato).toBe(1);
  });

  it('una etapa sin número llega como «sin dato» con su motivo, nunca como cero', async () => {
    apiRequest.mockResolvedValue(RESPUESTA);
    const d = await load(evento(''));
    const chats = d.etapas.find((/** @type {any} */ e) => e.clave === 'chats');
    expect(chats.valor).toBeNull();
    expect(chats.sinDato).toBe('motor sin consulta');
  });

  it('cada detenida lleva a donde se actúa', async () => {
    apiRequest.mockResolvedValue(RESPUESTA);
    const d = await load(evento(''));
    /** @param {string} g */
    const filas = (g) => d.detenidas.find((/** @type {any} */ x) => x.clave === g).filas;
    expect(filas('sin_abrir')[0].destino.href).toBe('/leads/L1');
    expect(filas('abierto_sin_enviar')[0].destino.href).toBeNull();
    expect(filas('esperando_decision')[0].destino.href).toBe('/instalaciones');
    expect(filas('aprobada_sin_instalar')[0].destino.href).toBe('/tickets/C5');
    expect(filas('aprobada_sin_instalar')[1].destino.href).toBe('/instalaciones?estado=aprobada');
    expect(filas('aprobada_sin_instalar')[1].motivoTexto).toMatch(/Sin ticket/);
  });

  it('un rango válido viaja tal cual; uno roto cae a 30 días antes de preguntar', async () => {
    apiRequest.mockResolvedValue(RESPUESTA);
    await load(evento('?desde=2026-10-01&hasta=2026-10-31'));
    expect(apiRequest.mock.calls[0][0]).toBe('/leads/embudo/?desde=2026-10-01&hasta=2026-10-31');
    expect(periodoDe(new URLSearchParams('dias=15'))).toEqual({ dias: 30, desde: '', hasta: '' });
    expect(periodoDe(new URLSearchParams('desde=ayer&hasta=hoy')).dias).toBe(30);
  });

  it('un 403 es un aviso de permiso, no una pantalla rota', async () => {
    apiRequest.mockRejectedValue(Object.assign(new Error('Forbidden'), { status: 403 }));
    const d = await load(evento(''));
    expect(d.sinPermiso).toBe(true);
    expect(d.error).toMatch(/gestión/);
    expect(d.etapas).toEqual([]);
  });
});

describe('/leads/[id]: la solicitud del prospecto', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('trae estado legible y los enlaces a Instalaciones y al ticket', async () => {
    apiRequest.mockResolvedValue({
      solicitudes: [{ id: 's1', estado: 'aprobada', caso_id: 'C1', abierta_en: '2026-11-01T10:00:00Z' }]
    });
    const r = await leerSolicitudesDelLead(cookies, 'L1');
    expect(apiRequest.mock.calls[0][0]).toBe('/leads/L1/solicitud/');
    expect(r.solicitudes[0]).toMatchObject({
      estadoTexto: 'Aprobada',
      hrefInstalaciones: '/instalaciones?estado=aprobada',
      hrefTicket: '/tickets/C1'
    });
  });

  it('si no se puede leer, la ficha sigue sin el bloque', async () => {
    apiRequest.mockRejectedValue(new Error('boom'));
    const r = await leerSolicitudesDelLead(cookies, 'L1');
    expect(r.solicitudes).toEqual([]);
    expect(r.error).toBe('boom');
  });
});
