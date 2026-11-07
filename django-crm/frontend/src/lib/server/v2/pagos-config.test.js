import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * El puente de lo que un cliente puede usar para pagar: el link y los otros medios.
 *
 * Lo que se afirma es el EFECTO: que un link que no es https limpio, o un medio
 * pasado del tope, NO salga al motor (el motor tampoco se lo daría a un cliente,
 * pero acá se avisa a quien lo escribe), que vacío QUITE la variable en vez de
 * guardar un vacío (el motor rechaza un valor vacío), y que leer nunca tire.
 */
const { envMock } = vi.hoisted(() => ({ /** @type {Record<string, string>} */ envMock: {} }));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const {
  leerAjustesDePago,
  guardarLinkDePago,
  guardarMediosDePago,
  validarLinkDePago,
  validarMediosDePago,
  leerMediosGuardados,
  VARIABLE_LINK_DE_PAGO,
  VARIABLE_MEDIOS_DE_PAGO
} = await import('./pagos-config.js');

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

describe('leerAjustesDePago', () => {
  it('devuelve el link cargado y, sin medios guardados, la lista vacía', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ variables: { LINK_DE_PAGO: 'https://pagos.ejemplo.co' } })
    });
    expect(await leerAjustesDePago(LOCALS, fetchMock)).toEqual({
      link: 'https://pagos.ejemplo.co',
      medios: [],
      medios_ilegibles: false
    });
  });
  it('trae los medios guardados en la misma lectura', async () => {
    const guardado = JSON.stringify([{ nombre: 'Efecty', instruccion: 'Convenio 12345. Di tu cedula.' }]);
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ variables: { MEDIOS_DE_PAGO: guardado } }) });
    const r = await leerAjustesDePago(LOCALS, fetchMock);
    expect(r?.medios).toEqual([{ nombre: 'Efecty', instruccion: 'Convenio 12345. Di tu cedula.' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('un valor guardado que no se puede leer se MARCA, no se muestra como vacío', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ variables: { MEDIOS_DE_PAGO: 'no es json' } }) });
    const r = await leerAjustesDePago(LOCALS, fetchMock);
    expect(r?.medios).toEqual([]);
    expect(r?.medios_ilegibles).toBe(true);
  });
  it('sin las variables devuelve link vacío, no null: el asistente sí contestó', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ variables: { OTRA: 'x' } }) });
    expect(await leerAjustesDePago(LOCALS, fetchMock)).toEqual({ link: '', medios: [], medios_ilegibles: false });
  });
  it('manda el tenant del servidor', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ variables: {} }) });
    await leerAjustesDePago(LOCALS, fetchMock);
    expect(fetchMock.mock.calls[0][0]).toContain('tenant=rapilink');
  });
  it('devuelve null --sin tirar-- si el motor falla o no hay asistente', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(leerAjustesDePago(LOCALS, fetchMock)).resolves.toBeNull();
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) });
    await expect(leerAjustesDePago(LOCALS, fetchMock)).resolves.toBeNull();
    delete envMock.PRIVATE_ASISTENTE_URL;
    fetchMock.mockClear();
    await expect(leerAjustesDePago(LOCALS, fetchMock)).resolves.toBeNull();
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

describe('validarMediosDePago', () => {
  it('acepta un medio y lo devuelve aplanado, con el número intacto', () => {
    const r = validarMediosDePago([{ nombre: '  Efecty ', instruccion: 'Convenio 12345.\n\tDi tu   cedula.' }]);
    expect(r).toEqual({
      ok: true,
      medios: [{ nombre: 'Efecty', instruccion: 'Convenio 12345. Di tu cedula.' }]
    });
  });
  it('una fila vacía por completo se ignora (la que queda al apretar Agregar)', () => {
    const r = validarMediosDePago([
      { nombre: '', instruccion: '' },
      { nombre: 'Banco', instruccion: 'Cuenta 000' },
      { nombre: ' ', instruccion: ' ' }
    ]);
    expect(r).toEqual({ ok: true, medios: [{ nombre: 'Banco', instruccion: 'Cuenta 000' }] });
  });
  it('sin ninguna fila es válido: significa quitar todos', () => {
    expect(validarMediosDePago([])).toEqual({ ok: true, medios: [] });
  });
  it.each([
    [{ nombre: '', instruccion: 'Convenio 1' }, /falta el nombre/],
    [{ nombre: 'Efecty', instruccion: '' }, /falta decir c/],
    [{ nombre: 'N'.repeat(61), instruccion: 'x' }, /pasa de 60/],
    [{ nombre: 'Efecty', instruccion: 'i'.repeat(301) }, /pasa de 300/]
  ])('una fila a medias o pasada del tope es un ERROR con motivo, no se descarta callada (%#)', (fila, motivo) => {
    const r = validarMediosDePago([fila]);
    expect(r.ok).toBe(false);
    expect(/** @type {any} */ (r).error).toMatch(motivo);
  });
  it('más de diez es un error', () => {
    const filas = Array.from({ length: 11 }, (_, i) => ({ nombre: 'M' + i, instruccion: 'ok' }));
    expect(validarMediosDePago(filas).ok).toBe(false);
  });
  it('un valor que no es texto no pasa por texto', () => {
    expect(validarMediosDePago([{ nombre: 5, instruccion: {} }])).toEqual({ ok: true, medios: [] });
  });
});

describe('leerMediosGuardados', () => {
  it('aplica las mismas reglas del motor: lo que el motor descartaría no se muestra', () => {
    const crudo = JSON.stringify([
      { nombre: 'Efecty', instruccion: 'Convenio 12345.' },
      { nombre: 'Sin texto', instruccion: '' },
      { nombre: 'X', instruccion: 'i'.repeat(301) },
      'no soy un par'
    ]);
    expect(leerMediosGuardados(crudo)).toEqual({
      medios: [{ nombre: 'Efecty', instruccion: 'Convenio 12345.' }],
      ilegible: false
    });
  });
  it('ausente o vacío no es ilegible; roto o de otra forma sí', () => {
    expect(leerMediosGuardados(undefined)).toEqual({ medios: [], ilegible: false });
    expect(leerMediosGuardados('  ')).toEqual({ medios: [], ilegible: false });
    expect(leerMediosGuardados('{')).toEqual({ medios: [], ilegible: true });
    expect(leerMediosGuardados('{}')).toEqual({ medios: [], ilegible: true });
  });
  it('no devuelve más de diez', () => {
    const crudo = JSON.stringify(Array.from({ length: 25 }, (_, i) => ({ nombre: 'M' + i, instruccion: 'ok' })));
    expect(leerMediosGuardados(crudo).medios).toHaveLength(10);
  });
});

describe('guardarMediosDePago', () => {
  it('hace PUT a la variable MEDIOS_DE_PAGO con la lista como JSON y el tenant del servidor', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    await guardarMediosDePago(LOCALS, fetchMock, [{ nombre: 'Efecty', instruccion: 'Convenio 12345.' }]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`http://motor:5000/configuracion/variables/${VARIABLE_MEDIOS_DE_PAGO}`);
    expect(init.method).toBe('PUT');
    const cuerpo = JSON.parse(init.body);
    expect(cuerpo.tenant).toBe('rapilink');
    expect(JSON.parse(cuerpo.valor)).toEqual([{ nombre: 'Efecty', instruccion: 'Convenio 12345.' }]);
  });
  it('sin ningún medio QUITA la variable (DELETE): el motor no acepta un valor vacío', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    await guardarMediosDePago(LOCALS, fetchMock, [{ nombre: '', instruccion: '' }]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('DELETE');
    expect(url).toContain(`/configuracion/variables/${VARIABLE_MEDIOS_DE_PAGO}?tenant=rapilink`);
  });
  it('una fila a medias NO sale al motor, y el error dice cuál', async () => {
    await expect(guardarMediosDePago(LOCALS, fetchMock, [{ nombre: 'Efecty', instruccion: '' }])).rejects.toThrow(/Efecty/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('el link y los medios se guardan en variables DISTINTAS', () => {
    expect(VARIABLE_MEDIOS_DE_PAGO).not.toBe(VARIABLE_LINK_DE_PAGO);
  });
  it('si el motor rechaza, el mensaje llega a quien lo escribió', async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({ error: 'config invalida: y' }) });
    await expect(guardarMediosDePago(LOCALS, fetchMock, [{ nombre: 'A', instruccion: 'b' }])).rejects.toThrow('config invalida: y');
  });
});
