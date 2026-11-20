import { describe, it, expect, vi, beforeEach } from 'vitest';

// La capa servidor de /tickets/approvals (12/11/2026). Lo que se protege: que
// las claves nuevas del backend lleguen a la página. La lección del 29/09
// (CLAUDE.md §6): `requiere_noc` viajaba bien desde el backend y esta capa lo
// dejaba caer, con el backend en verde.

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { listApprovals } = await import('./approvals.js');

const event = /** @type {any} */ ({ cookies: { get: () => 'token' } });

/** Una fila tal como la devuelve GET /cases/approvals/ (ApprovalInboxView). */
function fila(extra = {}) {
  return {
    id: 'a1',
    state: 'pending',
    note: 'Dexter intentó cerrar este caso y la regla «Cierre» pide una aprobación antes.',
    reason: '',
    created_at: '2026-11-12T15:00:00Z',
    decided_at: null,
    can_act: true,
    is_own_request: false,
    requested_by: { id: 'p-dexter', email: 'motor@empresa.test' },
    approver: null,
    case_summary: { id: 'c1', name: 'Sin internet', priority: 'Normal', account: null },
    rule_summary: { id: 'r1', name: 'Cierre', approver_role: 'MANAGER', approvers: [] },
    ...extra
  };
}

describe('listApprovals', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('lleva «Dexter» como solicitante y avisa que se cierra sola', async () => {
    apiRequest.mockImplementation(async (/** @type {string} */ url) =>
      url.startsWith('/cases/approvals/')
        ? { approvals: [fila({ origen: 'agente', solicitante: 'Dexter', cerrar_al_aprobar: true })] }
        : { rules: [] }
    );
    const { approvals } = await listApprovals(event);
    expect(approvals[0].requested_by).toBe('Dexter');
    expect(approvals[0].origen).toBe('agente');
    expect(approvals[0].cierra_al_aprobar).toBe(true);
    expect(approvals[0].note).toContain('Dexter intentó cerrar');
  });

  it('una persona sigue mostrándose por su correo', async () => {
    apiRequest.mockImplementation(async (/** @type {string} */ url) =>
      url.startsWith('/cases/approvals/')
        ? { approvals: [fila({ origen: 'persona', solicitante: null, cerrar_al_aprobar: false })] }
        : { rules: [] }
    );
    const { approvals } = await listApprovals(event);
    expect(approvals[0].requested_by).toBe('motor@empresa.test');
    expect(approvals[0].origen).toBe('persona');
    expect(approvals[0].cierra_al_aprobar).toBe(false);
  });
});
