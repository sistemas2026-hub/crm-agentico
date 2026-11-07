import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * El puente del link de pago.
 *
 * Lo que se afirma es el EFECTO: que un link que no es https limpio NO salga al
 * motor (el motor tampoco se lo daría a un cliente, pero acá se avisa a quien lo
 * escribe), que vacío QUITE la variable en vez de guardar un vacío (el motor
 * rechaza un valor vacío), y que leer nunca tire.
 */
const { envMock } = vi.hoisted(() => ({ /** @type {Record<string, string>} */ envMock: {} }));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { leerLinkDePago, guardarLinkDePago, validarLinkDePago, VARIABLE_LINK_DE_PAGO } =
  await import('./pagos-config.js');

const LOCALS = /** @type {any} */ ({ tenant: 'rapilink' });
let fetchMock = vi.fn();

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
  Object.assign(envMock, { PRIVATE_ASISTENTE_URL: 'http://motor:5000', PRIVATE_ASISTENTE_TENANT: 'rapilink' });
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock;
});
afterEach(() => vi.restoreAllMocks());

describe('validarLinkDePago', () => {
  it('acepta un https limpio y lo devuelve sin espacios alrededor', () => {
    expect(validarLinkDePago('  https://pagos.ejemplo.co/rapilink  ')).toEqual({
      ok: true,
      link: 'https://pagos.ejemplo.co/rapilink'
    });
  });
  it('vacío es válido: significa quitar el link', () => {
    expect(validarLinkDePago('')).toEqual({ ok: true, link: '' });
    expect(validarLinkDePago('   ')).toEqual({ ok: true, link: '' });
  });
  it.each([
    ['http://pagos.ejemplo.co', 'sin https'],
    ['pagos.ejemplo.co/x', 'sin esquema'],
    ['https://pagos.ejemplo.co/x y mas', 'con espacios'],
    ['https://usuario:clave@pagos.ejemplo.co/x', 'con usuario y clave incrustados'],
    ['javascript:alert(1)', 'esquema peligroso'],
    ['https://' + 'a'.repeat(600) + '.co', 'demasiado largo']
  ])('rechaza %s (%s)', (valor) => {
    const r = validarLinkDePago(valor);
    expect(r.ok).toBe(false);
    expect(/** @type {any} */ (r).error).toBeTruthy();
  });
});

describe('leerLinkDePago', () => {
  it('devuelve el link cargado', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ variables: { LINK_DE_PAGO: 'https://pagos.ejemplo.co' } })
    });
    expect(await leerLinkDePago(LOCALS, fetchMock)).toEqual({ link: 'https://pagos.ejemplo.co' });
  });
  it('sin la variable devuelve link vacío, no null: el asistente sí contestó', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ variables: { OTRA: 'x' } }) });
    expect(await leerLinkDePago(LOCALS, fetchMock)).toEqual({ link: '' });
  });
  it('manda el tenant del servidor', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ variables: {} }) });
    await leerLinkDePago(LOCALS, fetchMock);
    expect(fetchMock.mock.calls[0][0]).toContain('tenant=rapilink');
  });
  it('devuelve null --sin tirar-- si el motor falla o no hay asistente', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(leerLinkDePago(LOCALS, fetchMock)).resolves.toBeNull();
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) });
    await expect(leerLinkDePago(LOCALS, fetchMock)).resolves.toBeNull();
    delete envMock.PRIVATE_ASISTENTE_URL;
    fetchMock.mockClear();
    await expect(leerLinkDePago(LOCALS, fetchMock)).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('guardarLinkDePago', () => {
  it('con un link válido hace PUT a la variable LINK_DE_PAGO con el tenant del servidor', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    await guardarLinkDePago(LOCALS, fetchMock, 'https://pagos.ejemplo.co/x');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`http://motor:5000/configuracion/variables/${VARIABLE_LINK_DE_PAGO}`);
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({ tenant: 'rapilink', valor: 'https://pagos.ejemplo.co/x' });
  });
  it('vacío QUITA la variable (DELETE): el motor no acepta guardar un valor vacío', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    await guardarLinkDePago(LOCALS, fetchMock, '   ');
    const [url, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('DELETE');
    expect(url).toContain(`/configuracion/variables/${VARIABLE_LINK_DE_PAGO}?tenant=rapilink`);
  });
  it('un link que no es https limpio NO sale al motor', async () => {
    await expect(guardarLinkDePago(LOCALS, fetchMock, 'http://pagos.ejemplo.co')).rejects.toThrow(/https/);
    await expect(guardarLinkDePago(LOCALS, fetchMock, 'https://u:p@pagos.ejemplo.co')).rejects.toThrow(/usuario/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('si el motor rechaza, el mensaje del motor llega a quien lo escribió', async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({ error: 'config invalida: x' }) });
    await expect(guardarLinkDePago(LOCALS, fetchMock, 'https://pagos.ejemplo.co')).rejects.toThrow('config invalida: x');
  });
  it('sin asistente configurado lanza, y no sale a la red', async () => {
    delete envMock.PRIVATE_ASISTENTE_URL;
    await expect(guardarLinkDePago(LOCALS, fetchMock, 'https://pagos.ejemplo.co')).rejects.toThrow(/no configurado/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
