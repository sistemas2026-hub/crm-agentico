import { describe, it, expect, vi } from 'vitest';

/**
 * Las opciones de "Nuevo ticket" y "Editar ticket", en español.
 *
 * 28/10/2026: el formulario mostraba los rotulos crudos del CRM -- 'Normal',
 * 'Question', 'New' -- mientras el listado de al lado ya decia 'Alta' y
 * 'Pregunta'. Y la prioridad mas alta se llama 'Muy alta', como en WispHub,
 * donde el mismo ticket vive tambien. El VALOR que viaja sigue siendo el del
 * CRM: cambiarlo romperia el SLA y la importacion.
 */

const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (/** @type {any[]} */ ...a) => apiRequest(...a) }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const { getTicketFormOptions } = await import('$lib/server/v2/tickets.js');

const evento = /** @type {any} */ ({ cookies: { get: () => 'token' } });

describe('las opciones del formulario de ticket', () => {
  it('llegan en español, con el valor del CRM intacto', async () => {
    apiRequest.mockResolvedValue({
      status: [['New', 'New'], ['Closed', 'Closed']],
      priority: [['Low', 'Low'], ['Normal', 'Normal'], ['High', 'High'], ['Urgent', 'Urgent']],
      type_of_case: [['Question', 'Question'], ['Incident', 'Incident'], ['Problem', 'Problem']],
      accounts_list: [],
      contacts_list: [],
      users: []
    });
    const o = await getTicketFormOptions(evento);
    expect(o.priorities).toEqual([
      { value: 'Low', label: 'Baja' },
      { value: 'Normal', label: 'Normal' },
      { value: 'High', label: 'Alta' },
      { value: 'Urgent', label: 'Muy alta' }
    ]);
    expect(o.caseTypes.map((/** @type {any} */ t) => t.label)).toEqual([
      'Pregunta',
      'Incidente',
      'Problema'
    ]);
    expect(o.statuses).toEqual([
      { value: 'New', label: 'Nuevo' },
      { value: 'Closed', label: 'Cerrado' }
    ]);
  });

  it('un valor que no tiene traduccion se muestra como viene, no desaparece', async () => {
    apiRequest.mockResolvedValue({
      status: [['Escalated', 'Escalated']],
      priority: [],
      type_of_case: [],
      accounts_list: [],
      contacts_list: [],
      users: []
    });
    const o = await getTicketFormOptions(evento);
    expect(o.statuses).toEqual([{ value: 'Escalated', label: 'Escalated' }]);
  });
});
