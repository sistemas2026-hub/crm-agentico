import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * "NUEVO TICKET" TAMBIEN EN WISPHUB  --  26/10/2026
 *
 * Se afirma sobre lo que la accion HACE: que crea, en que orden, y a donde
 * manda a quien lleno el formulario. La regla que mas importa: un dato de
 * WispHub mal escrito NO deja un caso creado a medias -- se valida la forma
 * antes de crear nada.
 */

const createTicket = vi.fn();
const replyToTicket = vi.fn();
const crearEnWispHub = vi.fn();
const ASUNTOS = [{ asunto: 'No Tiene Internet', area: 'soporte_tecnico' }];
const leerAsuntosWispHub = vi.fn();
vi.mock('$lib/server/v2/tickets.js', () => ({
  createTicket: (...a) => createTicket(...a),
  replyToTicket: (...a) => replyToTicket(...a),
  getTicketFormOptions: async () => ({ defaults: {}, accounts: [], contacts: [], people: [] })
}));
vi.mock('$lib/server/v2/ticket-desde-dexter.js', () => ({
  leerAsuntosWispHub: (...a) => leerAsuntosWispHub(...a),
  crearEnWispHub: (...a) => crearEnWispHub(...a)
}));
vi.mock('$lib/server/v2/form-errors.js', () => ({ readableError: (_e, m) => m }));

const { actions, load } = await import('./+page.server.js');

/** @param {Record<string, any>} campos */
function evento(campos) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.set(k, v);
  return /** @type {any} */ ({
    cookies: {},
    request: { formData: async () => fd },
    locals: { user: { name: 'Ana', id: 'u-1' } },
    fetch: globalThis.fetch
  });
}

/** La accion termina con redirect(): se atrapa para leer a donde iba. */
async function correr(campos) {
  try {
    return { resultado: /** @type {any} */ (await actions.create(evento(campos))) };
  } catch (/** @type {any} */ r) {
    if (r?.location) return { destino: r.location };
    throw r;
  }
}

//  27/10/2026: el asunto del ticket ES uno de la lista de WispHub ('name'),
//  con la casilla o sin ella.
const BASE = { name: 'No Tiene Internet', description: 'El cliente llamo: sin internet.' };
const CON_WISPHUB = { ...BASE, en_wisphub: '1', servicio: '5832' };

describe('Nuevo ticket', () => {
  beforeEach(() => {
    createTicket.mockReset();
    crearEnWispHub.mockReset();
    createTicket.mockResolvedValue({ id: 'caso-1' });
    replyToTicket.mockReset();
    replyToTicket.mockResolvedValue({});
    leerAsuntosWispHub.mockReset();
    leerAsuntosWispHub.mockResolvedValue(ASUNTOS);
  });

  it('la carga trae los asuntos habilitados para WispHub', async () => {
    const d = /** @type {any} */ (await load(/** @type {any} */ ({ cookies: {}, url: new URL('http://x/tickets/new'), locals: {}, fetch })));
    expect(d.asuntosWispHub).toEqual([{ asunto: 'No Tiene Internet', area: 'soporte_tecnico' }]);
  });

  it('sin la casilla, no toca WispHub', async () => {
    const r = await correr(BASE);
    expect(createTicket).toHaveBeenCalledTimes(1);
    expect(crearEnWispHub).not.toHaveBeenCalled();
    expect(r.destino).toBe('/tickets/caso-1');
  });

  it.each([
    [{ servicio: '58 32' }, /dígitos/],
    [{ servicio: '' }, /dígitos/],
    [{ name: '' }, /asunto/],
    [{ name: 'Un asunto inventado' }, /lista de WispHub/],
    [{ description: '' }, /qué pasó/]
  ])('un dato de WispHub mal puesto NO crea nada, ni el caso (%o)', async (cambio, mensaje) => {
    const r = await correr({ ...CON_WISPHUB, ...cambio });
    expect(createTicket).not.toHaveBeenCalled();
    expect(crearEnWispHub).not.toHaveBeenCalled();
    expect(r.resultado.status).toBe(400);
    expect(r.resultado.data.error).toMatch(mensaje);
    // Lo que se escribio vuelve, para no tener que tipearlo de nuevo.
    expect(r.resultado.data.values.en_wisphub).toBe(true);
  });

  it('sin la casilla, un asunto fuera de la lista tampoco crea nada', async () => {
    const r = await correr({ ...BASE, name: 'Un asunto inventado' });
    expect(createTicket).not.toHaveBeenCalled();
    expect(r.resultado.data.error).toMatch(/lista de WispHub/);
  });

  it('sin lista (motor sin contestar) y sin la casilla, se crea solo aca con texto libre', async () => {
    leerAsuntosWispHub.mockResolvedValue([]);
    const r = await correr({ ...BASE, name: 'Un asunto escrito a mano' });
    expect(createTicket).toHaveBeenCalledTimes(1);
    expect(crearEnWispHub).not.toHaveBeenCalled();
    expect(r.destino).toBe('/tickets/caso-1');
  });

  //  ADJUNTO  --  27/10/2026
  const archivo = (bytes = 10) => new File([new Uint8Array(bytes)], 'foto.jpg', { type: 'image/jpeg' });

  it('sin archivo no sube nada', async () => {
    await correr(BASE);
    expect(replyToTicket).not.toHaveBeenCalled();
  });

  it('el archivo se sube al caso YA creado, sin texto (no es una respuesta)', async () => {
    crearEnWispHub.mockResolvedValue({ ok: true, idTicket: '95001', vinculado: true });
    const r = await correr({ ...CON_WISPHUB, attachment: archivo() });
    const [, caso, envio] = replyToTicket.mock.calls[0];
    expect(caso).toBe('caso-1');
    expect(envio.body).toBe('');
    expect(envio.file.name).toBe('foto.jpg');
    expect(createTicket.mock.invocationCallOrder[0]).toBeLessThan(
      replyToTicket.mock.invocationCallOrder[0]
    );
    expect(r.destino).toBe('/tickets/caso-1?wisphub=95001');
  });

  it('si el archivo no sube, el ticket queda y el detalle lo dice', async () => {
    replyToTicket.mockRejectedValue(new Error('x'));
    const r = await correr({ ...BASE, attachment: archivo() });
    const destino = new URL(`http://x${r.destino}`);
    expect(destino.pathname).toBe('/tickets/caso-1');
    expect(destino.searchParams.get('adjunto_error')).toBe('No se pudo subir el archivo.');
  });

  it('un archivo de mas de 25 MB no crea nada', async () => {
    const r = await correr({ ...BASE, attachment: archivo(25 * 1024 * 1024 + 1) });
    expect(createTicket).not.toHaveBeenCalled();
    expect(replyToTicket).not.toHaveBeenCalled();
    expect(r.resultado.data.error).toMatch(/25 MB/);
  });

  it('si el motor no contesta los asuntos, no crea nada y dice como seguir', async () => {
    leerAsuntosWispHub.mockResolvedValue([]);
    const r = await correr(CON_WISPHUB);
    expect(createTicket).not.toHaveBeenCalled();
    expect(r.resultado.data.error).toMatch(/Desmarcá la casilla/);
  });

  it('crea el caso PRIMERO y despues pide el de WispHub para ese caso', async () => {
    crearEnWispHub.mockResolvedValue({ ok: true, idTicket: '95001', vinculado: true });
    const r = await correr(CON_WISPHUB);
    expect(createTicket).toHaveBeenCalledTimes(1);
    expect(createTicket.mock.calls[0][1].name).toBe('No Tiene Internet');
    const [, , caso, datos] = crearEnWispHub.mock.calls[0];
    expect(caso).toBe('caso-1');
    expect(datos).toEqual({
      servicio: '5832',
      asunto: 'No Tiene Internet',
      descripcion: 'El cliente llamo: sin internet.'
    });
    expect(r.destino).toBe('/tickets/caso-1?wisphub=95001');
  });

  it('si se creo pero no quedo atado, el detalle lo dice', async () => {
    crearEnWispHub.mockResolvedValue({ ok: true, idTicket: '95001', vinculado: false });
    const r = await correr(CON_WISPHUB);
    expect(r.destino).toBe('/tickets/caso-1?wisphub=95001&wisphub_sin_atar=1');
  });

  it('si WispHub no lo creo, el caso queda y el detalle dice por que', async () => {
    crearEnWispHub.mockResolvedValue({ ok: false, motivo: 'Ese número de servicio no existe en WispHub.' });
    const r = await correr(CON_WISPHUB);
    const destino = new URL(`http://x${r.destino}`);
    expect(destino.pathname).toBe('/tickets/caso-1');
    expect(destino.searchParams.get('wisphub_error')).toBe(
      'Ese número de servicio no existe en WispHub.'
    );
  });
});
