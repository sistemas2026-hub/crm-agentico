import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * LO QUE HACE SOLO CADA AGENTE, EN /agentes  --  02/11/2026
 * =========================================================
 *
 * "Eso no deberia ir en cada agente... con un agente si pueda reiniciar y otro
 * no", dijo el usuario viendo /capacidad. La autonomia se decide ahora por
 * agente y se controla al lado de sus herramientas.
 *
 * Se protege la CADENA (CLAUDE.md §6): que el reporte del motor llegue entero
 * y con los mismos nombres -- 'por_agente' incluido --, que la pantalla se vea
 * igual si no se puede calcular, y que el agente viaje hasta el motor con el
 * autor de la SESION.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('$lib/server/v2/tenant.js', () => ({
  tenantDeLaSesion: async () => 'rapilink',
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'rapilink' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));
const supervisor = vi.hoisted(() => ({ leer: /** @type {any} */ (null) }));
vi.mock('$lib/server/v2/ajustes-supervisor.js', () => ({ leerAjustes: () => supervisor.leer() }));

const { load, actions } = await import('./+page.server.js');

// La forma EXACTA de GET /reportes/autonomia-ganada (nucleo/seguridad/autonomia_ganada.py).
const AUTONOMIA = {
  piso: { minimo_revisadas: 20, ventana_dias: 14, tasa_minima_aprobacion: 0.9 },
  acciones: [
    { accion: 'reiniciar_ont', candidata: true, no_candidata: [], elegible: true, no_critica: true,
      faltan: [], tasa_aprobacion: null,
      umbrales: { minimo_revisadas: 30, ventana_dias: 30, tasa_minima_aprobacion: 0.95 },
      evidencia: { revisadas: 0, rechazadas: 0, fallidas: 0, confirmadas: 0, no_confirmadas: 0,
                   no_verificables: 0, pendientes: 0 },
      desde: '2026-10-03T00:00:00+00:00',
      autonomia: { autonoma: false, estado: 'sin_registro', promocion_id: null },
      por_agente: {
        soporte: { autonoma: false, estado: 'retirada', promocion_id: null },
        soporte_tecnico_cliente: { autonoma: true, estado: 'activa', promocion_id: 'p5',
                                   desde: '2026-11-02T18:00:00+00:00', rol: 'soporte_tecnico_cliente' }
      } },
    { accion: 'registrar_pago', candidata: false, no_candidata: ['efecto_no_verificable', 'sin_previas_en_codigo'],
      elegible: false }
  ]
};

/** @param {string} [rol] */
const evento = (rol = 'ADMIN') => /** @type {any} */ ({
  locals: { profile: { role: rol } }, fetch: globalThis.fetch
});

describe('la autonomia llega a /agentes', () => {
  /** @param {boolean} [falla] */
  function motor(falla = false) {
    globalThis.fetch = /** @type {any} */ (vi.fn(async (url) => {
      const u = String(url);
      if (u.includes('/reportes/autonomia-ganada')) {
        return falla
          ? { ok: false, status: 500, json: async () => ({ error: 'No se pudo calcular la autonomia ganada.' }) }
          : { ok: true, status: 200, json: async () => structuredClone(AUTONOMIA) };
      }
      if (u.includes('/agentes/catalogo')) return { ok: true, status: 200, json: async () => ({ herramientas: [],
        motivos_escalada: [{ clave: 'solicitud_explicita', rotulo: 'Pidió hablar con una persona' }] }) };
      if (u.includes('/agentes')) return { ok: true, status: 200, json: async () => ({ agentes: [{ nombre: 'soporte' }] }) };
      return { ok: true, status: 200, json: async () => ({}) };
    }));
  }

  it('llega entera y con los mismos nombres, por_agente incluido', async () => {
    motor();
    const d = /** @type {any} */ (await load(evento()));
    expect(d.autonomia).toEqual(AUTONOMIA);
    expect(d.autonomia.acciones[0].por_agente.soporte_tecnico_cliente.autonoma).toBe(true);
    expect(d.esAdmin).toBe(true);
    //  Los motivos de escalada llegan al formulario con su rotulo (04/11/2026).
    expect(d.motivosEscalada).toEqual([{ clave: 'solicitud_explicita', rotulo: 'Pidió hablar con una persona' }]);
  });

  it('las tareas del Supervisor: cuales hace solo, para quien puede verlas', async () => {
    motor();
    supervisor.leer = async () => ({ tareas: [
      { clave: 'a', nombre: 'Pasar casos a Despacho', delegada: true },
      { clave: 'b', nombre: 'Armar la jornada', delegada: false }] });
    const admin = /** @type {any} */ (await load(evento()));
    expect(admin.tareasSupervisor).toEqual({ delegadas: ['Pasar casos a Despacho'], total: 2 });
    const usuario = /** @type {any} */ (await load(evento('USER')));
    expect(usuario.tareasSupervisor).toBeNull();
    supervisor.leer = async () => { throw new Error('CRM caido'); };
    const caido = /** @type {any} */ (await load(evento()));
    expect(caido.tareasSupervisor).toBeNull();
    expect(caido.agentes).toEqual([{ nombre: 'soporte' }]);
  });

  it('si el motor no la calcula, los agentes se ven igual', async () => {
    motor(true);
    const d = /** @type {any} */ (await load(evento('USER')));
    expect(d.agentes).toEqual([{ nombre: 'soporte' }]);
    expect(d.autonomia).toBeNull();
    expect(d.errorAutonomia).toMatch(/autonomia ganada/);
    expect(d.esAdmin).toBe(false);
  });
});

describe('que un agente haga sola una accion, o que vuelva a pedir aprobacion', () => {
  /** @type {any[]} */
  let pedidos;
  /** @type {any} */
  let contesta;
  beforeEach(() => {
    pedidos = [];
    contesta = { ok: true, status: 201, json: async () => ({ estado: 'activa', id: 'p1' }) };
    globalThis.fetch = /** @type {any} */ (vi.fn(async (url, opciones) => {
      pedidos.push({ url: String(url), cuerpo: JSON.parse(opciones?.body ?? '{}') });
      return contesta;
    }));
  });

  /** @param {Record<string, string>} campos @param {string} [rol] */
  function accion(campos, rol = 'ADMIN') {
    const f = new FormData();
    for (const [k, v] of Object.entries(campos)) f.set(k, v);
    return /** @type {any} */ ({
      locals: { profile: { role: rol }, user: { id: '7c9e6679-7425-40de-944b-e07fc1f90ae7', name: 'Ana Perez' } },
      fetch: globalThis.fetch,
      request: new Request('http://crm/agentes', { method: 'POST', body: f })
    });
  }

  it('promover viaja con la accion, EL AGENTE, y el autor y el rol de la SESION', async () => {
    const r = await actions.promover(accion({ accion: 'reiniciar_ont', rol: 'soporte_tecnico_cliente',
                                              confirmo: 'si' }));
    expect(pedidos).toEqual([{ url: 'http://motor/autonomia-ganada/promover', cuerpo: {
      tenant: 'rapilink', accion: 'reiniciar_ont', rol: 'soporte_tecnico_cliente', autor: 'Ana Perez',
      autor_usuario_id: '7c9e6679-7425-40de-944b-e07fc1f90ae7', autor_rol: 'ADMIN' } }]);
    expect(r).toEqual({ autonomia: { accion: 'reiniciar_ont', rol: 'soporte_tecnico_cliente', ok: 'promovida' } });
  });

  it('sin agente, vale para todos: no viaja ningun rol', async () => {
    await actions.promover(accion({ accion: 'reiniciar_ont', confirmo: 'si' }));
    expect(pedidos[0].cuerpo).not.toHaveProperty('rol');
  });

  it('sin la confirmacion, sin ser ADMIN, o con un agente que no es un nombre, no viaja nada', async () => {
    const r1 = /** @type {any} */ (await actions.promover(accion({ accion: 'reiniciar_ont', rol: 'soporte' })));
    const r2 = /** @type {any} */ (await actions.promover(accion({ accion: 'reiniciar_ont', confirmo: 'si' }, 'USER')));
    const r3 = /** @type {any} */ (await actions.promover(accion({ accion: 'reiniciar_ont', rol: 'Soporte; drop',
                                                                  confirmo: 'si' })));
    expect([r1.status, r2.status, r3.status]).toEqual([400, 403, 400]);
    expect(pedidos).toEqual([]);
  });

  it('si el motor dice que falta algo, se muestra lo que falta', async () => {
    contesta = { ok: false, status: 409, json: async () => ({ error: 'SIN_EVIDENCIA',
      faltan: [{ condicion: 'cero_fallidas', tiene: 1, necesita: 0 }] }) };
    const r = /** @type {any} */ (await actions.promover(accion({ accion: 'reiniciar_ont', rol: 'soporte',
                                                                 confirmo: 'si' })));
    expect(r.status).toBe(409);
    expect(r.data.autonomia.faltan).toEqual([{ condicion: 'cero_fallidas', tiene: 1, necesita: 0 }]);
  });

  it('un rechazo a proposito del motor se dice en palabras, con 409', async () => {
    contesta = { ok: false, status: 409, json: async () => ({ error: 'AGENTE_SIN_ESA_HERRAMIENTA' }) };
    const r = /** @type {any} */ (await actions.promover(accion({ accion: 'reiniciar_ont', rol: 'ventas',
                                                                 confirmo: 'si' })));
    expect(r.status).toBe(409);
    expect(r.data.autonomia.error).toBe('Este agente no usa esa herramienta.');
  });

  it('criticidad: no critica pide la casilla; viaja al motor con el autor de la sesion', async () => {
    const sin = /** @type {any} */ (await actions.criticidad(accion({ accion: 'reiniciar_ont', critica: 'no' })));
    expect(sin.status).toBe(400);
    expect(pedidos).toEqual([]);
    const usuario = /** @type {any} */ (await actions.criticidad(accion({ accion: 'reiniciar_ont', critica: 'si' }, 'USER')));
    expect(usuario.status).toBe(403);
    const r = await actions.criticidad(accion({ accion: 'reiniciar_ont', critica: 'no', confirmo: 'si' }));
    expect(pedidos[0].url).toBe('http://motor/agentes/herramientas/reiniciar_ont/critica');
    expect(pedidos[0].cuerpo).toMatchObject({ tenant: 'rapilink', critica: false, autor: 'Ana Perez',
                                              autor_rol: 'ADMIN' });
    expect(r).toEqual({ autonomia: { accion: 'reiniciar_ont', criticidad: true, ok: 'no_critica' } });
  });

  it('retirar exige un motivo y manda el agente', async () => {
    const sin = /** @type {any} */ (await actions.retirar(accion({ accion: 'reiniciar_ont', rol: 'soporte' })));
    expect(sin.status).toBe(400);
    expect(pedidos).toEqual([]);
    await actions.retirar(accion({ accion: 'reiniciar_ont', rol: 'soporte', motivo: ' no en soporte ' }));
    expect(pedidos[0].url).toBe('http://motor/autonomia-ganada/retirar');
    expect(pedidos[0].cuerpo).toMatchObject({ accion: 'reiniciar_ont', rol: 'soporte', motivo: 'no en soporte',
                                              autor: 'Ana Perez' });
  });
});
