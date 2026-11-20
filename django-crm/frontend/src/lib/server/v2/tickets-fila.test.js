import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * La fila de la cola de Tickets, tal como la arma `listTickets` desde el API.
 *
 * 20/10/2026 (auditor independiente): "lo que tengo asignado lo veo siempre"
 * miraba solo `assignee_id`, que es el PRIMER responsable. Un caso donde la
 * persona era el segundo llegaba del API y la pantalla lo descartaba. La fila
 * lleva ahora `assignee_ids`, con todos.
 */

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const { listTickets } = await import('$lib/server/v2/tickets.js');

const evento = /** @type {any} */ ({ cookies: { get: () => 'token' } });

describe('la fila de la cola', () => {
  beforeEach(() => apiRequest.mockReset());

  it('lleva a TODOS los responsables, no solo al primero', async () => {
    apiRequest.mockResolvedValue({
      cases: [{
        id: 'c-1', name: 'No tiene internet', status: 'New', priority: 'Normal',
        assigned_to: [{ id: 'p-cartera' }, { id: 'p-soporte' }]
      }]
    });

    const { results } = await listTickets(evento, new URLSearchParams());

    expect(results[0].assignee_id).toBe('p-cartera');
    expect(results[0].assignee_ids).toEqual(['p-cartera', 'p-soporte']);
    expect(results[0].assignee_count).toBe(2);
  });

  it('sin responsables, la lista viene vacia y no null', async () => {
    apiRequest.mockResolvedValue({ cases: [{ id: 'c-2', name: 'x', status: 'New' }] });

    const { results } = await listTickets(evento, new URLSearchParams());

    expect(results[0].assignee_ids).toEqual([]);
    expect(results[0].assignee_id).toBeNull();
  });
});
