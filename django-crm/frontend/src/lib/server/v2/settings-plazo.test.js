import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * CONFIGURACION NO ESPERA AL MOTOR  --  26/10/2026
 * ===============================================
 *
 * "Ya abrio pero demora", dijo el usuario. Las 21 lecturas del hub iban en un
 * solo Promise.all: la pagina no se dibujaba hasta que llegaba la ultima, y
 * ocho van al motor, que comparte sus 8 hilos con los turnos de WhatsApp.
 *
 * Se afirma el EFECTO: con una lectura del motor que no contesta nunca, la
 * carga responde igual -- lo del CRM ya viene --, lo del motor llega aparte,
 * la tarjeta colgada queda sin valor al vencer el plazo, y las demas traen el
 * suyo.
 */

const nunca = () => new Promise(() => {});
const motorLento = vi.hoisted(() => ({ asistente: /** @type {any} */ (null) }));

vi.mock('./asistente-config.js', () => ({
  leerConfiguracionAsistente: () => motorLento.asistente()
}));
vi.mock('./canal-whatsapp.js', () => ({
  leerCanalWhatsapp: async () => ({ activo: true, numero_visible: '+57 300' })
}));
vi.mock('./smartolt.js', () => ({ leerSmartOlt: async () => null }));
vi.mock('./planes-venta.js', () => ({ contarPlanesVenta: async () => ({ cantidad: 6 }) }));
vi.mock('./oferta.js', () => ({ leerOferta: async () => null }));
vi.mock('./guias-tv.js', () => ({ leerGuiasTV: async () => null }));
vi.mock('./credenciales.js', () => ({
  leerCredenciales: async () => ({
    disponible: true,
    credenciales: [{ cargado: true }, { declarado: true, cargado: false }]
  })
}));
vi.mock('./bandeja-config.js', () => ({
  leerAjustesBandeja: async () => null,
  // Dos claves sin rótulo en dos familias: la tarjeta tiene que decir 2.
  leerRotulosBandeja: async () => ({
    sin_rotulo: { motivos: ['frustracion_detectada'], etiquetas: [], casos: ['problema_de_tv'] }
  })
}));
vi.mock('./avisos-campo.js', () => ({ leerAvisos: async () => ({ canales: [1, 2] }) }));
vi.mock('./business-hours.js', () => ({ getBusinessHours: async () => ({ calendar: {} }) }));
vi.mock('./custom-fields.js', () => ({ getCustomFields: async () => ({ totals: {} }) }));
vi.mock('./escalation.js', () => ({ getEscalationPolicies: async () => ({ policies: [] }) }));
vi.mock('./inbound-email.js', () => ({
  getMailboxes: async () => ({ totals: {}, mailboxes: [] })
}));
vi.mock('./macros.js', () => ({ getMacros: async () => ({ totals: {} }) }));
vi.mock('./organization.js', () => ({ getOrgSettings: async () => ({ org: { name: 'X' } }) }));
vi.mock('./reopen.js', () => ({ getReopenPolicy: async () => ({ policy: null }) }));
vi.mock('./routing.js', () => ({ getRoutingRules: async () => ({ totals: {} }) }));
vi.mock('./tags.js', () => ({ getTags: async () => ({ totals: {} }) }));
vi.mock('./team.js', () => ({ listTeam: async () => ({ forbidden: true }) }));
vi.mock('./ticket-approvals.js', () => ({
  getApprovalRules: async () => ({ rules: [], totals: {} })
}));
vi.mock('./tokens.js', () => ({ listOrgTokens: async () => ({ forbidden: true }) }));

const { getSettingsHub, conPlazo, PLAZO_MOTOR_MS } = await import('./settings.js');

const evento = /** @type {any} */ ({ locals: {}, fetch: globalThis.fetch, cookies: {} });

describe('conPlazo', () => {
  it('devuelve lo que llega a tiempo', async () => {
    expect(await conPlazo(Promise.resolve(7), 50)).toBe(7);
  });
  it('null si falla, sin rechazar', async () => {
    expect(await conPlazo(Promise.reject(new Error('caido')), 50)).toBeNull();
  });
  it('null si no contesta dentro del plazo', async () => {
    expect(await conPlazo(nunca(), 20)).toBeNull();
  });
});

describe('getSettingsHub', () => {
  beforeEach(() => {
    vi.useRealTimers();
    motorLento.asistente = nunca;
  });

  it('EL EFECTO: responde sin esperar al motor, y lo del motor llega aparte', async () => {
    vi.useFakeTimers();
    //  Si la carga esperara al motor, este await no terminaria nunca: la
    //  lectura del asistente no contesta y el reloj esta detenido.
    const data = await getSettingsHub(evento);
    expect(data.org).toEqual({ name: 'X' });
    expect(data.avisosCampo).toEqual({ cuantos: 2 });
    expect(data.motor).toBeInstanceOf(Promise);

    await vi.advanceTimersByTimeAsync(PLAZO_MOTOR_MS + 10);
    const motor = await data.motor;
    expect(motor.asistente).toBeNull(); // la colgada, sin valor
    expect(motor.canalWhatsapp).toEqual({ activo: true, numero_visible: '+57 300' });
    expect(motor.planesVenta).toEqual({ cantidad: 6 });
    expect(motor.credencialesTotales).toEqual({ cargadas: 1, faltan: 1 });
    // Las claves sin rótulo se cuentan entre las tres familias (29/10/2026).
    expect(motor.sinRotulo).toBe(2);
  });

  it('con el motor al dia, todo llega', async () => {
    motorLento.asistente = async () => ({ roles: ['ventas'], persona: {} });
    const data = await getSettingsHub(evento);
    const motor = await data.motor;
    expect(motor.asistente).toEqual({ roles: ['ventas'], persona: {} });
  });
});
