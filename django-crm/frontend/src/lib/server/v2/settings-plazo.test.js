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
//  Las tres lecturas del CRM que cada prueba puede colgar o romper. Las demas
//  contestan siempre.
const crm = vi.hoisted(() => ({
  escalamiento: /** @type {any} */ (null),
  macros: /** @type {any} */ (null),
  reapertura: /** @type {any} */ (null)
}));

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
// Lectura del motor sumada al hub el 31/10/2026 (df9c190c). Sin este mock el
// archivo no cargaba: importa motor-headers.js, que pide $env, y la prueba
// entera dejaba de correr.
vi.mock('./organizacion-config.js', () => ({ leerOrganizacion: async () => null }));
// 12/11/2026: UNA lectura de variables alimenta dos filas (Variables y Pagos).
// pagos-config se sustituye por lo mismo que exporta: el real importa
// motor-headers.js, que pide $env. La regla de lectura de los medios se
// prueba en pagos-config.test.js.
vi.mock('./variables-empresa.js', () => ({
  leerVariables: async () => ({
    variables: { LINK_DE_PAGO: 'https://pagos.x', MEDIOS_DE_PAGO: '[1,2]', OTRA: 'y' },
    usos: {},
    faltan: { FALTA_UNA: ['h'] }
  })
}));
vi.mock('./pagos-config.js', () => ({
  VARIABLE_LINK_DE_PAGO: 'LINK_DE_PAGO',
  VARIABLE_MEDIOS_DE_PAGO: 'MEDIOS_DE_PAGO',
  leerMediosGuardados: (/** @type {string} */ c) => ({ medios: JSON.parse(c), ilegible: false })
}));
vi.mock('./avisos-campo.js', () => ({ leerAvisos: async () => ({ canales: [1, 2] }) }));
vi.mock('./business-hours.js', () => ({ getBusinessHours: async () => ({ calendar: {} }) }));
vi.mock('./custom-fields.js', () => ({ getCustomFields: async () => ({ totals: {} }) }));
vi.mock('./escalation.js', () => ({ getEscalationPolicies: () => crm.escalamiento() }));
vi.mock('./inbound-email.js', () => ({
  getMailboxes: async () => ({ totals: {}, mailboxes: [] })
}));
vi.mock('./macros.js', () => ({ getMacros: () => crm.macros() }));
vi.mock('./organization.js', () => ({ getOrgSettings: async () => ({ org: { name: 'X' } }) }));
vi.mock('./reopen.js', () => ({ getReopenPolicy: () => crm.reapertura() }));
vi.mock('./routing.js', () => ({ getRoutingRules: async () => ({ totals: {} }) }));
vi.mock('./tags.js', () => ({ getTags: async () => ({ totals: {} }) }));
vi.mock('./team.js', () => ({ listTeam: async () => ({ forbidden: true }) }));
vi.mock('./ticket-approvals.js', () => ({
  getApprovalRules: async () => ({ rules: [], totals: {} })
}));
vi.mock('./tokens.js', () => ({ listOrgTokens: async () => ({ forbidden: true }) }));

const { getSettingsHub, conPlazo, PLAZO_MOTOR_MS, PLAZO_CRM_MS } = await import('./settings.js');

const evento = /** @type {any} */ ({
  locals: { org: { name: 'Rapilink' } },
  fetch: globalThis.fetch,
  cookies: {}
});

/** Un error como el que lanza apiRequest: el estado HTTP en `.status`. */
const errorHttp = (status) => Object.assign(new Error(`HTTP ${status}`), { status });

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
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    motorLento.asistente = nunca;
    crm.escalamiento = async () => ({ policies: [] });
    crm.macros = async () => ({ totals: { org: 3 } });
    crm.reapertura = async () => ({ policy: { is_enabled: true } });
  });

  it('EL EFECTO: responde sin esperar al motor, y lo del motor llega aparte', async () => {
    vi.useFakeTimers();
    //  Si la carga esperara al motor, este await no terminaria nunca: la
    //  lectura del asistente no contesta y el reloj esta detenido.
    const data = await getSettingsHub(evento);
    expect(await data.organizacion).toEqual({ name: 'X' });
    expect(await data.avisosCampo).toEqual({ cuantos: 2 });
    expect(data.motor).toBeInstanceOf(Promise);

    await vi.advanceTimersByTimeAsync(PLAZO_MOTOR_MS + 10);
    const motor = await data.motor;
    expect(motor.asistente).toBeNull(); // la colgada, sin valor
    expect(motor.canalWhatsapp).toEqual({ activo: true, numero_visible: '+57 300' });
    expect(motor.planesVenta).toEqual({ cantidad: 6 });
    expect(motor.credencialesTotales).toEqual({ cargadas: 1, faltan: 1 });
    // Las claves sin rótulo se cuentan entre las tres familias (29/10/2026).
    expect(motor.sinRotulo).toBe(2);
    //  Pagos ya no es siempre null: sale de la misma lectura que Variables.
    expect(motor.pagos).toEqual({ link: true, medios: 2 });
    expect(motor.variables).toEqual({ cantidad: 3, faltan: 1 });
  });

  it('con el motor al dia, todo llega', async () => {
    motorLento.asistente = async () => ({ roles: ['ventas'], persona: {} });
    const data = await getSettingsHub(evento);
    const motor = await data.motor;
    expect(motor.asistente).toEqual({ roles: ['ventas'], persona: {} });
  });

  it('EL EFECTO: responde sin esperar al CRM, y una lectura colgada no frena a las demas', async () => {
    vi.useFakeTimers();
    //  01/11/2026: "la ventana configuracion demora para abrir o en ocasiones
    //  no abre". La pagina esperaba las trece lecturas del CRM juntas, sin
    //  plazo. Con escalamiento sin contestar y el reloj detenido, este await
    //  no terminaria nunca si la carga lo esperara.
    crm.escalamiento = nunca;
    const data = await getSettingsHub(evento);
    //  El nombre de la empresa sale de la sesion: el encabezado no espera.
    expect(data.orgNombre).toBe('Rapilink');
    //  Cada lectura llega por su lado: las que contestan no esperan a la colgada.
    expect(await data.macroTotals).toEqual({ org: 3 });
    expect(await data.organizacion).toEqual({ name: 'X' });
    const colgada = data.escalationTotals;
    expect(colgada).toBeInstanceOf(Promise);
    await vi.advanceTimersByTimeAsync(PLAZO_CRM_MS + 10);
    expect(await colgada).toBeNull(); // sin valor, no un error
  });

  it('EL EFECTO: una lectura del CRM que falla no tumba la pagina', async () => {
    //  Antes un error en cualquiera de las trece se propagaba: la pagina
    //  entera mostraba error. Ahora esa fila queda sin valor.
    crm.macros = async () => {
      throw errorHttp(500);
    };
    const data = await getSettingsHub(evento);
    expect(await data.macroTotals).toBeNull();
    expect(await data.organizacion).toEqual({ name: 'X' });
    //  Y queda dicho en el log cual fue, sin datos de nadie.
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('macros'),
    );
  });

  it('la reapertura de un miembro (403) queda sin valor, como antes', async () => {
    crm.reapertura = async () => {
      throw errorHttp(403);
    };
    const data = await getSettingsHub(evento);
    expect(await data.reopen).toBeNull();
  });

  it('con todo al dia, los totales llegan resumidos como antes', async () => {
    crm.escalamiento = async () => ({
      policies: [
        { is_active: false, breaches_last_30d: { first_response: 2, resolution: 1 } },
        { is_active: true, first_response_action: 'notify', first_response_target: 5,
          resolution_action: 'reassign', resolution_target: 7, breaches_last_30d: {} }
      ]
    });
    const data = await getSettingsHub(evento);
    expect(await data.escalationTotals).toEqual({ active: 1, count: 2, breaches_unhandled_30d: 3 });
    expect(await data.reopen).toEqual({ is_enabled: true });
    expect(await data.peopleTotals).toBeNull(); // forbidden
  });
});
