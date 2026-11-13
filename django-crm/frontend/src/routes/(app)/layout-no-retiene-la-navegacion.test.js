import { describe, it, expect, vi } from 'vitest';

/**
 * EL MENÚ NO RETIENE LA NAVEGACIÓN  --  04/11/2026
 *
 * "Configuración demora o no muestra nada al abrir." Al navegar dentro de la
 * app, SvelteKit no cambia de pantalla hasta que termina el load de este
 * layout, y ese load esperaba siete conteos del CRM sin plazo: el clic no
 * mostraba nada hasta que contestaba el más lento. Se afirma el EFECTO: con
 * un conteo que no contesta nunca, el load termina igual, dentro del plazo,
 * con las demás insignias puestas y esa sin insignia (no con un número viejo
 * ni con un error).
 */
const nunca = () => new Promise(() => {});
const { lento } = vi.hoisted(() => ({ lento: { tickets: /** @type {any} */ (null) } }));

vi.mock('$lib/server/v2/leads.js', () => ({ listLeads: async () => ({ totals: { count: 4 } }) }));
vi.mock('$lib/server/v2/deals.js', () => ({ listDeals: async () => ({ totals: { count: 2 } }) }));
vi.mock('$lib/server/v2/tickets.js', () => ({
  listTickets: () => lento.tickets(),
  OPEN_STATUSES: ['open']
}));
vi.mock('$lib/server/v2/tasks.js', () => ({ listTasks: async () => ({ totals: { open: 3 } }) }));
vi.mock('$lib/server/v2/invoices.js', () => ({ listInvoices: async () => ({ totals: { action_needed: 1 } }) }));
vi.mock('$lib/server/v2/approvals.js', () => ({ countAwaitingApprovals: async () => 5 }));
vi.mock('$lib/server/v2/notifications.js', () => ({ countUnread: async () => 6 }));
vi.mock('$lib/server/v2/organization.js', () => ({
  getOrgShell: async () => ({ terminology: { 'lead.plural': 'Prospectos' }, logo_url: undefined })
}));

// Las insignias de trabajo humano (12/11/2026): Supervisor sin clave = una
// fuente que no se pudo leer. El menú no tiene que inventarle un 0.
vi.mock('$lib/server/v2/hoy-operacion.js', () => ({
  insigniasDeTrabajo: async () => ({ conversaciones: 7, instalaciones: 2 })
}));

const { load } = await import('./+layout.server.js');
// El mismo valor que el layout (no se puede exportar desde un +layout.server.js:
// SvelteKit rechaza exports que no sean suyos). Si el layout lo sube, esta
// prueba lo nota: el load no habría terminado al avanzar este reloj.
const PLAZO_CONTEO_MS = 2000;

const evento = () => /** @type {any} */ ({
  locals: { org: { id: 'o', name: 'Rapilink' }, profile: { role: 'USER' }, org_settings: {} },
  cookies: {},
  fetch: vi.fn()
});

describe('el load del layout de la app', () => {
  it('EL EFECTO: un conteo que no contesta no retiene la navegación', async () => {
    vi.useFakeTimers();
    try {
      lento.tickets = nunca;
      const promesa = load(evento());
      //  Si el load esperara al conteo colgado, este await no terminaría nunca:
      //  el reloj está detenido y `tickets` no contesta.
      await vi.advanceTimersByTimeAsync(PLAZO_CONTEO_MS + 10);
      const shell = /** @type {any} */ (await promesa);
      expect(shell.counts).toEqual({
        leads: 4, pipeline: 2, tasks: 3, invoices: 1, approvals: 5, notifications: 6,
        conversaciones: 7, instalaciones: 2
      });
      expect(shell.counts.supervisor).toBeUndefined();
      expect(shell.counts.tickets).toBeUndefined();
      expect(shell.org.name).toBe('Rapilink');
      expect(shell.org.terminology).toEqual({ 'lead.plural': 'Prospectos' });
    } finally {
      vi.useRealTimers();
    }
  });

  it('con el CRM al día, todas las insignias llegan', async () => {
    lento.tickets = async () => ({ totals: { open: 9 } });
    const shell = /** @type {any} */ (await load(evento()));
    expect(shell.counts.tickets).toBe(9);
  });

});
