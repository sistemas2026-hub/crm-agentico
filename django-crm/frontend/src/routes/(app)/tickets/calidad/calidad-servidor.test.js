import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * «Calidad de la atención» (28/10/2026): quién la ve y qué período pide.
 * Mide por persona, así que un colaborador no la carga; y el período se cuenta
 * hasta HOY en la zona de la empresa, no en la del servidor.
 */

const leerResumenEncuestas = vi.fn();
vi.mock('$lib/server/v2/encuestas.js', () => ({
  leerResumenEncuestas: (...a) => leerResumenEncuestas(...a)
}));
vi.mock('$lib/server/v2/areas.js', () => ({ leerAreas: async () => ({ areas: [{ nombre: 'soporte_tecnico', etiqueta: 'Soporte técnico' }] }) }));
vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({
  zonaDeLaEmpresa: async () => 'America/Bogota',
  diaEn: () => '2026-10-28'
}));

const { load } = await import('./+page.server.js');

/** @param {string} rol @param {string} [q] */
const evento = (rol, q = '') =>
  /** @type {any} */ ({
    locals: { profile: { role: rol } },
    fetch: vi.fn(),
    cookies: {},
    url: new URL(`http://x/tickets/calidad${q}`)
  });

describe('Calidad de la atención', () => {
  beforeEach(() => {
    leerResumenEncuestas.mockReset();
    leerResumenEncuestas.mockResolvedValue({ total: { enviadas: 0 } });
  });

  it('un colaborador no la carga: ni siquiera se le pide al motor', async () => {
    const d = /** @type {any} */ (await load(evento('USER')));
    expect(d.puedeVer).toBe(false);
    expect(d.resumen).toBeNull();
    expect(leerResumenEncuestas).not.toHaveBeenCalled();
  });

  it.each(['ADMIN', 'SUPERVISOR', 'OPERACIONES'])('%s la ve', async (rol) => {
    const d = /** @type {any} */ (await load(evento(rol)));
    expect(d.puedeVer).toBe(true);
    expect(leerResumenEncuestas).toHaveBeenCalledTimes(1);
  });

  it('por omisión, los últimos 30 días hasta hoy en la empresa (con hoy incluido)', async () => {
    const d = /** @type {any} */ (await load(evento('ADMIN')));
    expect(d.dias).toBe(30);
    expect(leerResumenEncuestas.mock.calls[0][2]).toEqual({ desde: '2026-09-29', hasta: '2026-10-28' });
    //  El área se muestra con su nombre, no con la clave interna.
    expect(d.etiquetasArea).toEqual({ soporte_tecnico: 'Soporte técnico' });
  });

  it('7 días: desde hace 6 hasta hoy; un período que no se ofrece cae a 30', async () => {
    await load(evento('ADMIN', '?dias=7'));
    expect(leerResumenEncuestas.mock.calls[0][2]).toEqual({ desde: '2026-10-22', hasta: '2026-10-28' });
    const d = /** @type {any} */ (await load(evento('ADMIN', '?dias=999')));
    expect(d.dias).toBe(30);
  });
});
