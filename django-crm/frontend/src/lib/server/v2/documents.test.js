import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * El estado de ingesta de un documento LLEGA a la pantalla.
 *
 * Hasta el 12/11/2026 `toDoc` no copiaba `usar_en_asistente`, `estado_ingesta`,
 * `ingesta_fragmentos`, `ingesta_detalle` ni `roles_asistente`, aunque el
 * serializer de Django los manda y la lista los lee: el indicador «N
 * fragmentos / No se pudo indexar / Indexando…» no se dibujó nunca. Es el
 * patrón de CLAUDE.md §6 (`requiere_noc`): el backend en verde, la capa
 * servidor del frontend dejando caer el dato. Por eso la prueba atraviesa
 * `listDocuments` entera con la respuesta tal como viene del backend y afirma
 * sobre lo que recibe la página.
 */

vi.mock('$env/dynamic/private', () => ({ env: {} }));
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...a) => apiRequest(...a) }));

const { listDocuments } = await import('./documents.js');

const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const token = `${b64({ alg: 'HS256' })}.${b64({ role: 'USER', user_id: 'u1' })}.x`;
/** Solo `get`: es lo único que la lectura usa de las cookies. */
const cookies = /** @type {any} */ ({ get: (n) => (n === 'jwt_access' ? token : undefined) });

function fila(extra) {
  return {
    id: 'd1',
    title: 'Manual de instalación',
    document_file: '/media/manual.pdf',
    status: 'active',
    created_by: { id: 'u1', name: 'Ana' },
    created_at: '2026-11-01T10:00:00Z',
    shared_to: [],
    teams: [],
    ...extra
  };
}

beforeEach(() => apiRequest.mockReset());

describe('lo que la lista necesita para dibujar el estado de ingesta', () => {
  it('un documento indexado llega con sus fragmentos y sus roles', async () => {
    apiRequest.mockResolvedValue({
      documents_active: {
        documents_active: [
          fila({ usar_en_asistente: true, roles_asistente: 'soporte, ventas', estado_ingesta: 'ok', ingesta_fragmentos: 14 })
        ]
      },
      documents_inactive: { documents_inactive: [] }
    });
    const { results } = await listDocuments({ cookies });
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({
      usar_en_asistente: true,
      roles_asistente: 'soporte, ventas',
      estado_ingesta: 'ok',
      ingesta_fragmentos: 14
    });
  });

  it('uno que falló llega con el motivo, para poder mostrarlo', async () => {
    apiRequest.mockResolvedValue({
      documents_active: {
        documents_active: [
          fila({ usar_en_asistente: true, estado_ingesta: 'error', ingesta_detalle: 'El motor no respondió' })
        ]
      },
      documents_inactive: { documents_inactive: [] }
    });
    const { results } = await listDocuments({ cookies });
    expect(results[0].estado_ingesta).toBe('error');
    expect(results[0].ingesta_detalle).toBe('El motor no respondió');
  });

  it('uno que no usa el asistente no inventa un estado', async () => {
    apiRequest.mockResolvedValue({
      documents_active: { documents_active: [fila({})] },
      documents_inactive: { documents_inactive: [] }
    });
    const { results } = await listDocuments({ cookies });
    expect(results[0].usar_en_asistente).toBe(false);
    expect(results[0].estado_ingesta).toBe('');
    expect(results[0].ingesta_fragmentos).toBeNull();
  });
});
