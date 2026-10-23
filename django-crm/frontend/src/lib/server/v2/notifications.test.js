/**
 * `resolvedLink` NO es un formateador: es una guarda.
 *
 * `Notification.link` es una columna de texto, y lo que se guarda ahí termina
 * como el `href` de un enlace que alguien va a tocar. La función existe para
 * que un valor cualquiera no pueda convertirse en un `http(s)://…` externo ni
 * en un `javascript:`, o sea para que una fila de la base no sea un redirect
 * abierto.
 *
 * Por eso se prueba sobre el EFECTO —qué devuelve ante lo que NO debería
 * pasar— y no solo sobre el camino feliz. Al agregar el enlace del ciclo de la
 * madrugada la función dejó de reconocer un único patrón, que es justo cuando
 * una guarda así se afloja sin que nadie lo note.
 */
import { describe, it, expect, vi } from 'vitest';

// El módulo importa `apiRequest`, que a su vez lee el entorno de SvelteKit.
// Acá no se prueba ninguna llamada: se prueba la guarda del enlace, que es
// una función pura. Mismo mock que `programacion-noc.test.js`.
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: vi.fn() }));
vi.mock('$env/dynamic/private', () => ({ env: {} }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const { PRODUCED_VERBS, resolvedLink } = await import('./notifications.js');

describe('resolvedLink · lo que SÍ reconoce', () => {
  it('un ticket, en su forma actual', () => {
    expect(resolvedLink('/tickets/abc-123')).toBe('/tickets/abc-123');
  });

  it('y en la vieja, que apuntaba al mismo ticket', () => {
    expect(resolvedLink('/cases/abc-123')).toBe('/tickets/abc-123');
  });

  it('la jornada de un día', () => {
    expect(resolvedLink('/supervisor-noc/cuadrillas?dia=2026-10-06&reparto=1'))
      .toBe('/supervisor-noc/cuadrillas?dia=2026-10-06&reparto=1');
  });

  it('la jornada aunque la fila guardada no traiga el resto de la query', () => {
    // Se RECONSTRUYE desde la fecha: lo que se devuelve no es lo que estaba
    // guardado, y por eso llega completo igual.
    expect(resolvedLink('/supervisor-noc/cuadrillas?dia=2026-10-06'))
      .toBe('/supervisor-noc/cuadrillas?dia=2026-10-06&reparto=1');
  });
});

describe('resolvedLink · lo que NO puede dejar pasar', () => {
  const peligrosos = [
    'http://evil.example/roba',
    'https://evil.example/roba',
    '//evil.example/roba',
    'javascript:alert(1)',
    '/supervisor-noc/cuadrillas?dia=javascript:alert(1)',
    '/supervisor-noc/cuadrillas?dia=../../admin',
    '/supervisor-noc/cuadrillas?dia=2026-13-99x',
    'https://evil.example/supervisor-noc/cuadrillas?dia=2026-10-06',
    '/otra/pantalla?dia=2026-10-06'
  ];

  for (const link of peligrosos) {
    it(`devuelve '' para ${link}`, () => {
      expect(resolvedLink(link)).toBe('');
    });
  }

  it("y para lo que no es texto", () => {
    expect(resolvedLink(null)).toBe('');
    expect(resolvedLink(undefined)).toBe('');
    expect(resolvedLink({ toString: () => '/tickets/x' })).toBe('');
  });
});

describe('PRODUCED_VERBS', () => {
  it('incluye el ciclo de la madrugada', () => {
    // Sin esto la fila se marca como "no producer" y se muestra como un
    // identificador crudo en vez de un aviso legible.
    expect(PRODUCED_VERBS).toContain('reparto_de_la_madrugada');
  });

  it('y no perdió los que ya había', () => {
    expect(PRODUCED_VERBS).toContain('case.mentioned');
    expect(PRODUCED_VERBS).toContain('case.commented');
  });
});
