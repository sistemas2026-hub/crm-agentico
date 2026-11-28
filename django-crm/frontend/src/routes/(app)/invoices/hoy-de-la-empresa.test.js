import { describe, it, expect, vi } from 'vitest';

/**
 * LAS FACTURAS ABREN EN EL DÍA DE LA EMPRESA (27/10/2026)
 *
 * La fecha de emisión (factura) y la de inicio (recurrente) salían de
 * `new Date().toISOString()`: el día de UTC, que desde las 19:00 de Bogotá es
 * mañana. Ahora la carga devuelve `hoy` de `hoyDeLaEmpresa`, y la página lo
 * usa como valor inicial. Se afirma que la carga lo devuelve —con un día
 * distinto a propósito del de hoy— para las dos pantallas.
 */

vi.mock('$lib/server/v2/hoy-de-la-empresa.js', () => ({ hoyDeLaEmpresa: async () => '2001-02-03' }));
vi.mock('$lib/server/v2/accounts.js', () => ({ listAccounts: async () => ({ results: [] }) }));
vi.mock('$lib/server/v2/contacts.js', () => ({ listContacts: async () => ({ results: [] }) }));
vi.mock('$lib/server/v2/products.js', () => ({ listProducts: async () => ({ results: [] }) }));
vi.mock('$lib/server/v2/invoices.js', () => ({ createInvoice: vi.fn() }));
vi.mock('$lib/server/v2/recurring.js', () => ({ createRecurringInvoice: vi.fn() }));

const factura = await import('./new/+page.server.js');
const recurrente = await import('./recurring/new/+page.server.js');

const evento = /** @type {any} */ ({ cookies: {}, locals: { org: { id: 'o' } } });

describe('el día con que abren las facturas', () => {
  it('una factura nueva', async () => {
    const d = /** @type {any} */ (await factura.load(evento));
    expect(d.hoy).toBe('2001-02-03');
  });

  it('una factura recurrente nueva', async () => {
    const d = /** @type {any} */ (await recurrente.load(evento));
    expect(d.hoy).toBe('2001-02-03');
  });
});
