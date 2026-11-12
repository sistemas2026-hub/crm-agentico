import { describe, it, expect, vi, beforeEach } from 'vitest';

/*
 * La capa servidor del hilo del cliente (12/11/2026). Afirma sobre lo que
 * RECIBE la página, con la respuesta del backend tal como la arma
 * `campo/hilo_del_cliente.py`: la lección de `requiere_noc` (CLAUDE.md §6) es
 * que un campo puede viajar bien del backend y caerse acá.
 */
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor' } }));
vi.mock('./tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa_a' }));
vi.mock('./motor-headers.js', () => ({ headersMotor: () => ({ 'X-Token': 't' }) }));
// La lista de personas de la organización, de donde sale el Profile.id de quien
// mira (el JWT no lo trae). `resolveMe` es el real: empareja por correo.
const gente = vi.fn();
vi.mock('./org-people.js', async (orig) => ({
  ...(/** @type {any} */ (await orig())),
  getOrgPeopleAndTeams: (/** @type {any[]} */ ...a) => gente(...a)
}));

const { leerOrdenesDelCaso, leerHiloDeOrden, leerFichaDelCliente, conversacionDelCaso } =
  await import('./hilo-del-cliente.js');

const CASO = '11111111-2222-3333-4444-555555555555';
const ORDEN = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

/** Una fila como la arma `resumen_de_orden`. */
const FILA = {
  id: ORDEN, numero: 188, tipo: 'Correctivo', estado_operativo: 'bloqueada',
  estado_etiqueta: 'Bloqueada', estado_validacion: 'sin_evaluar', prioridad: 'alta',
  tecnico: 'Carlos Gómez', integrantes: 2, cuadrilla: 'Cuadrilla Norte',
  fecha: '2026-11-12', programada_para: '2026-11-12T13:00:00+00:00',
  completada_campo_en: null, cerrada_en: null, caso_id: CASO, puede_abrir: false
};

beforeEach(() => {
  apiRequest.mockReset();
  gente.mockReset();
  gente.mockResolvedValue({ people: [] });
});

describe('el bloque «Campo» del ticket', () => {
  it('pide al backend por el caso y entrega cada fila entera', async () => {
    apiRequest.mockResolvedValue({ caso_id: CASO, servicio: '4986', ordenes: [FILA] });
    const { datos, error } = await leerOrdenesDelCaso({ cookies: {} }, CASO);
    expect(apiRequest.mock.calls[0][0]).toBe(`/campo/casos/${CASO}/ordenes/`);
    expect(error).toBeNull();
    expect(datos?.servicio).toBe('4986');
    // Ningún campo se pierde en el camino: cuadrilla, fecha y puede_abrir llegan.
    expect(datos?.ordenes[0]).toEqual(FILA);
  });

  it('un id que no es UUID no llega al backend', async () => {
    const { error } = await leerOrdenesDelCaso({ cookies: {} }, '../trabajos');
    expect(apiRequest).not.toHaveBeenCalled();
    expect(error?.status).toBe(404);
  });

  it('un 403 del backend se dice como permiso, no como «sin visitas»', async () => {
    apiRequest.mockImplementationOnce(() => Promise.reject(Object.assign(new Error('x'), { status: 403 })));
    const { datos, error } = await leerOrdenesDelCaso({ cookies: {} }, CASO);
    expect(datos).toBeNull();
    expect(error?.codigo).toBe('SIN_PERMISO');
  });
});

describe('la página de la orden', () => {
  it('pide el hilo y lo entrega tal cual', async () => {
    const hilo = { ...FILA, caso: { id: CASO, nombre: 'No tiene internet' }, servicio: '4986',
      evidencias: [{ id: 'e1', nombre: 'foto.jpg' }] };
    apiRequest.mockResolvedValue(hilo);
    const { datos } = await leerHiloDeOrden({ cookies: {} }, ORDEN);
    expect(apiRequest.mock.calls[0][0]).toBe(`/campo/trabajos/${ORDEN}/hilo/`);
    expect(datos).toEqual(hilo);
  });

  it('otra empresa (404) se dice como «no existe»', async () => {
    apiRequest.mockImplementationOnce(() => Promise.reject(Object.assign(new Error('x'), { status: 404 })));
    const { error } = await leerHiloDeOrden({ cookies: {} }, ORDEN);
    expect(error?.codigo).toBe('NO_ENCONTRADA');
  });
});

describe('la ficha del cliente junta el CRM y el motor', () => {
  it('las dos mitades llegan, y el rol viaja al motor para recortar la ficha', async () => {
    const crm = { servicio: '4986', tickets: [{ id: CASO }], ordenes: [FILA], solicitudes: null };
    apiRequest.mockResolvedValue(crm);
    const motor = { servicio: '4986', conversaciones: [{ id: 'c1', canal: 'whatsapp' }],
      contexto: { cliente: { nombre: 'Ana' }, equipo: { estado: 'Online' } } };
    const fetch = vi.fn(async () => ({ ok: true, json: async () => motor }));
    const r = await leerFichaDelCliente(
      { cookies: {}, locals: { profile: { role: 'USER' } }, fetch: /** @type {any} */ (fetch) }, '4986');
    expect(apiRequest.mock.calls[0][0]).toBe('/campo/clientes/4986/');
    const url = new URL(String(/** @type {any} */ (fetch.mock.calls[0])[0]));
    expect(url.pathname).toBe('/clientes/4986/ficha');
    expect(url.searchParams.get('tenant')).toBe('empresa_a');
    expect(url.searchParams.get('rol')).toBe('USER');
    expect(r.crm).toEqual(crm);
    expect(r.motor).toEqual(motor);
    expect(r.error).toBeNull();
  });

  it('el perfil de quien mira viaja al motor: sin él, ADMIN recibiría el defecto restringido', async () => {
    apiRequest.mockResolvedValue({ servicio: '4986', tickets: [], ordenes: [], solicitudes: [] });
    gente.mockResolvedValue({ people: [{ id: 'perfil-9', email: 'ana@rapilink' }] });
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    await leerFichaDelCliente({
      cookies: {}, locals: { profile: { role: 'ADMIN' }, user: { email: 'Ana@Rapilink' } },
      fetch: /** @type {any} */ (fetch)
    }, '4986');
    const url = new URL(String(/** @type {any} */ (fetch.mock.calls[0])[0]));
    expect(url.searchParams.get('rol')).toBe('ADMIN');
    expect(url.searchParams.get('perfil')).toBe('perfil-9');
  });

  it('si la lista de personas falla, la ficha se pide igual, sin perfil', async () => {
    apiRequest.mockResolvedValue({ servicio: '4986', tickets: [], ordenes: [], solicitudes: [] });
    gente.mockRejectedValue(new Error('caído'));
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    await leerFichaDelCliente({
      cookies: {}, locals: { profile: { role: 'USER' }, user: { email: 'x@y' } },
      fetch: /** @type {any} */ (fetch)
    }, '4986');
    const url = new URL(String(/** @type {any} */ (fetch.mock.calls[0])[0]));
    expect(url.searchParams.get('perfil')).toBeNull();
    expect(url.searchParams.get('rol')).toBe('USER');
  });

  it('sin motor, la ficha sale igual con lo del CRM', async () => {
    apiRequest.mockResolvedValue({ servicio: '4986', tickets: [], ordenes: [], solicitudes: [] });
    const fetch = vi.fn(async () => { throw new Error('caído'); });
    const r = await leerFichaDelCliente({ cookies: {}, locals: {}, fetch: /** @type {any} */ (fetch) }, '4986');
    expect(r.motor).toBeNull();
    expect(r.crm?.servicio).toBe('4986');
  });

  it('un servicio con barras no sale ni al CRM ni al motor', async () => {
    const fetch = vi.fn();
    const r = await leerFichaDelCliente({ cookies: {}, locals: {}, fetch: /** @type {any} */ (fetch) }, '1/../x');
    expect(apiRequest).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
    expect(r.error?.status).toBe(404);
  });
});

describe('la conversación de un caso', () => {
  it('devuelve solo el id, sin pedir la ficha técnica', async () => {
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ conversacion: { id: 'c9' } }) }));
    const id = await conversacionDelCaso({}, /** @type {any} */ (fetch), CASO);
    expect(id).toBe('c9');
    const url = new URL(String(/** @type {any} */ (fetch.mock.calls[0])[0]));
    expect(url.searchParams.has('servicio')).toBe(false);
  });
});
