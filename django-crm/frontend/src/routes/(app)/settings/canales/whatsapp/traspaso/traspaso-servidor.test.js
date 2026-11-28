import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Traspaso a una persona y cierre por inactividad (12/11/2026).
 *
 * Se prueba la CADENA hasta el motor sin dobles de la capa servidor: el
 * formulario entra a la acción, pasa por `traspaso-config.js` REAL, y lo que
 * se afirma es el cuerpo que llega al motor y lo que vuelve a la página. Solo
 * se sustituyen el tenant de la sesión y `fetch`. CLAUDE.md §6: un dato que la
 * capa servidor deja caer no lo ve ninguna prueba del backend.
 */
vi.mock('$lib/server/v2/tenant.js', () => ({
  destinoDelAsistente: async () => ({ baseUrl: 'http://motor', tenant: 'empresa' })
}));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: (h = {}) => h }));

const { load, actions } = await import('./+page.server.js');

//  La forma EXACTA que devuelve GET /configuracion/traspaso (api.py::_traspaso_de).
const DEL_MOTOR = {
  textos: {
    mensaje: 'Te paso con un asesor.',
    mensajes_por_motivo: { frustracion_detectada: 'Entiendo tu molestia.' },
    mensaje_ya_escalada: 'Tu caso ya está con alguien.',
    mensaje_si_falla: 'Escribime de nuevo.',
    frases_de_traspaso: ['un asesor']
  },
  motivos: ['frustracion_detectada', 'tres_fallos_seguidos'],
  cierre: { habilitado: true, horas_inactividad_cierra: 24, rollout_cutoff: '2026-09-22T15:58:07+00:00',
            backfill_habilitado: false, backfill_lote: 10 },
  sin_gestion_horas: 12
};

/** @type {any[]} */
let pedidos;
/** @type {(url: string, init: any) => any} */
let responder;

beforeEach(() => {
  pedidos = [];
  responder = (url) => {
    if (url.includes('/configuracion/bandeja/rotulos')) {
      return { ok: true, json: async () => ({ rotulos: { frustracion_detectada: 'Frustración' } }) };
    }
    return { ok: true, json: async () => structuredClone(DEL_MOTOR) };
  };
});

const fetchFalso = vi.fn(async (/** @type {string} */ url, /** @type {any} */ init) => {
  pedidos.push({ url, init, cuerpo: init?.body ? JSON.parse(init.body) : null });
  return responder(url, init);
});

/** @param {Record<string, string>} campos @param {string} [rol] */
function evento(campos, rol = 'ADMIN') {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.append(k, v);
  return /** @type {any} */ ({ fetch: fetchFalso, request: { formData: async () => fd },
    locals: { profile: { role: rol } } });
}

describe('traspaso: del motor a la página', () => {
  it('la carga entrega lo del motor sin renombrar, con los rótulos de la Bandeja', async () => {
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ fetch: fetchFalso, locals: { profile: { role: 'USER' } } })));
    expect(d.traspaso).toEqual(DEL_MOTOR);
    expect(d.rotulos).toEqual({ frustracion_detectada: 'Frustración' });
    expect(d.can_edit).toBe(false);
    expect(pedidos.some((p) => p.url === 'http://motor/configuracion/traspaso?tenant=empresa')).toBe(true);
  });

  it('si el motor no contesta, la página recibe null (no se cae)', async () => {
    responder = () => { throw new Error('ECONNREFUSED'); };
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ fetch: fetchFalso, locals: {} })));
    expect(d.traspaso).toBeNull();
  });
});

describe('traspaso: de la página al motor', () => {
  it('los textos viajan con las CINCO claves, los motivos y las frases una por línea', async () => {
    const r = /** @type {any} */ (await actions.textos(evento({
      mensaje: '  Te paso con un asesor.  ',
      'motivo:frustracion_detectada': 'Entiendo.',
      'motivo:tres_fallos_seguidos': '',
      mensaje_ya_escalada: 'Ya está con alguien.',
      mensaje_si_falla: '',
      frases_de_traspaso: 'un asesor\n\n  te paso con  \n'
    })));
    expect(r).toEqual({ textos: { ok: true } });
    const p = pedidos.at(-1);
    expect(p.url).toBe('http://motor/configuracion/traspaso/textos');
    expect(p.init.method).toBe('PUT');
    expect(p.cuerpo).toEqual({
      tenant: 'empresa',
      mensaje: 'Te paso con un asesor.',
      mensajes_por_motivo: { frustracion_detectada: 'Entiendo.', tres_fallos_seguidos: '' },
      mensaje_ya_escalada: 'Ya está con alguien.',
      mensaje_si_falla: '',
      frases_de_traspaso: ['un asesor', 'te paso con']
    });
  });

  it('el motivo del rechazo del motor vuelve a la página tal cual', async () => {
    responder = () => ({ ok: false, json: async () => ({ error: 'el mensaje para quien vuelve a escribir no puede ser igual al anuncio' }) });
    const r = /** @type {any} */ (await actions.textos(evento({ mensaje: 'x', mensaje_ya_escalada: 'x' })));
    expect(r.status).toBe(400);
    expect(r.data.textos.error).toContain('igual al anuncio');
  });

  it('sin mensaje general no sale nada', async () => {
    const r = /** @type {any} */ (await actions.textos(evento({ mensaje: '   ' })));
    expect(r.status).toBe(400);
    expect(pedidos).toHaveLength(0);
  });

  it('quien no es administrador no cambia nada, ni textos ni cierre', async () => {
    const a = /** @type {any} */ (await actions.textos(evento({ mensaje: 'x' }, 'USER')));
    const b = /** @type {any} */ (await actions.cierre(evento({ horas_inactividad_cierra: '24' }, 'BODEGA')));
    expect(a.status).toBe(403);
    expect(b.status).toBe(403);
    expect(pedidos).toHaveLength(0);
  });

  it('el cierre viaja con las cuatro claves; vacío en horas es null, no 0', async () => {
    await actions.cierre(evento({ habilitado: 'on', horas_inactividad_cierra: '48', backfill_lote: '20' }));
    expect(pedidos.at(-1).cuerpo).toEqual({
      tenant: 'empresa', habilitado: true, horas_inactividad_cierra: 48,
      backfill_habilitado: false, backfill_lote: 20
    });
    await actions.cierre(evento({ horas_inactividad_cierra: '', backfill_lote: '10' }));
    expect(pedidos.at(-1).cuerpo.horas_inactividad_cierra).toBeNull();
    expect(pedidos.at(-1).cuerpo.habilitado).toBe(false);
  });

  it('horas que no son un entero positivo no llegan al motor', async () => {
    for (const malo of ['0', '-3', '2.5', 'un día']) {
      const r = /** @type {any} */ (await actions.cierre(evento({ horas_inactividad_cierra: malo })));
      expect(r.status).toBe(400);
    }
    expect(pedidos).toHaveLength(0);
  });
});
