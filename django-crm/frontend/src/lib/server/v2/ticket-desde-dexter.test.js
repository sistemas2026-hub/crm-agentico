import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Lo que la pantalla le manda al motor para crear el ticket en WispHub.
 *
 * El autor sale de la SESION, nunca del formulario, y el numero de ticket no
 * viaja de aca para alla: lo lee el motor de la respuesta de WispHub.
 */

vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_ASISTENTE_URL: 'http://motor:5000' } }));
vi.mock('$lib/server/v2/tenant.js', () => ({ tenantDeLaSesion: async () => 'empresa' }));
vi.mock('$lib/server/v2/motor-headers.js', () => ({ headersMotor: () => ({ 'X-Servicio-Token': 't' }) }));

const { crearEnWispHub, titularDelServicio, MOTIVOS } = await import('./ticket-desde-dexter.js');

const locals = /** @type {any} */ ({ user: { name: 'Ana Operadora', id: 'u-1' } });

/** @param {number} status @param {any} cuerpo */
const respuesta = (status, cuerpo) => ({ ok: status < 300, status, json: async () => cuerpo });

describe('crearEnWispHub', () => {
  /** @type {any[]} */
  let pedidos;
  beforeEach(() => {
    pedidos = [];
  });

  it('manda el autor de la sesion y ningun numero de ticket', async () => {
    const fetch = /** @type {any} */ (async (url, init) => {
      pedidos.push({ url, cuerpo: JSON.parse(init.body) });
      return respuesta(201, { id_ticket: '95001', vinculado: true });
    });
    const r = await crearEnWispHub(locals, fetch, 'caso-1', {
      servicio: '5832', asunto: 'No Tiene Internet', descripcion: 'x'
    });
    expect(r).toEqual({ ok: true, idTicket: '95001', vinculado: true });
    expect(pedidos[0].url).toBe('http://motor:5000/casos/caso-1/ticket-operativo');
    expect(pedidos[0].cuerpo).toEqual({
      tenant: 'empresa', servicio: '5832', asunto: 'No Tiene Internet', descripcion: 'x',
      autor: 'Ana Operadora', autor_usuario_id: 'u-1'
    });
    expect('external_ticket_id' in pedidos[0].cuerpo).toBe(false);
  });

  it('el archivo viaja al motor y la respuesta dice si llego al ISP', async () => {
    const fetch = /** @type {any} */ (async (url, init) => {
      pedidos.push({ url, cuerpo: JSON.parse(init.body) });
      return respuesta(201, { id_ticket: '95001', vinculado: true, adjunto: false });
    });
    const archivo = { nombre: 'foto.jpg', tipo: 'image/jpeg', base64: 'anBn' };
    const r = await crearEnWispHub(locals, fetch, 'caso-1', {
      servicio: '5832', asunto: 'No Tiene Internet', descripcion: 'x', archivo
    });
    expect(pedidos[0].cuerpo.archivo).toEqual(archivo);
    expect(r).toEqual({ ok: true, idTicket: '95001', vinculado: true, adjunto: false });
  });

  it('traduce el motivo del motor', async () => {
    const fetch = /** @type {any} */ (async () => respuesta(404, { error: 'SERVICIO_NO_EXISTE' }));
    const r = await crearEnWispHub(locals, fetch, 'caso-1', { servicio: '1', asunto: 'a', descripcion: 'x' });
    expect(r).toEqual({ ok: false, motivo: MOTIVOS.SERVICIO_NO_EXISTE });
  });

  it('si la espera se corta, NO dice que no se creo: dice que no se pudo confirmar', async () => {
    const fetch = /** @type {any} */ (async () => {
      throw new DOMException('timeout', 'TimeoutError');
    });
    const r = await crearEnWispHub(locals, fetch, 'caso-1', { servicio: '1', asunto: 'a', descripcion: 'x' });
    expect(r).toEqual({ ok: false, motivo: MOTIVOS.INCIERTO });
  });
});

describe('titularDelServicio', () => {
  it('un numero mal escrito ni siquiera sale al motor', async () => {
    const fetch = vi.fn();
    const r = await titularDelServicio(locals, /** @type {any} */ (fetch), '58-32');
    expect(r).toEqual({ ok: false, motivo: MOTIVOS.SERVICIO_INVALIDO });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('devuelve solo nombre y estado', async () => {
    const fetch = /** @type {any} */ (async () =>
      respuesta(200, { nombre: 'Cliente', estado: 'Activo', cedula: 'no-deberia' }));
    const r = await titularDelServicio(locals, fetch, '5832');
    expect(r).toEqual({ ok: true, nombre: 'Cliente', estado: 'Activo' });
  });
});
