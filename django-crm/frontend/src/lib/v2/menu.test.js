import { describe, it, expect } from 'vitest';
import { gruposDelMenu } from './menu.js';
import { MODULOS_OCULTABLES, ocultosConocidos } from './modulos.js';

/**
 * El menú que se dibuja, por rol y por lo que la empresa ocultó (12/11/2026).
 * Se afirma sobre los destinos que salen, no sobre la presencia de una bandera.
 */
const destinos = (grupos) => grupos.flatMap((g) => g.items.map((i) => i.href));

describe('módulos visibles por empresa', () => {
  it('el catálogo son las nueve claves del backend, en su orden (common/modulos.py)', () => {
    expect(MODULOS_OCULTABLES.map((m) => m.clave)).toEqual([
      'accounts', 'contacts', 'solutions', 'documents', 'tasks',
      'pipeline', 'goals', 'invoices', 'timesheet'
    ]);
  });

  it('sin nada oculto el menú sale entero, con los nueve módulos', () => {
    const d = destinos(gruposDelMenu({ role: 'ADMIN', ocultos: [] }));
    for (const m of MODULOS_OCULTABLES) expect(d).toContain(m.href);
  });

  it('lo oculto no se dibuja y lo demás sigue', () => {
    const d = destinos(gruposDelMenu({ role: 'ADMIN', ocultos: ['accounts', 'timesheet'] }));
    expect(d).not.toContain('/accounts');
    expect(d).not.toContain('/timesheet');
    expect(d).toContain('/contacts');
    expect(d).toContain('/invoices');
    expect(d).toContain('/conversaciones');
  });

  it('un grupo que queda vacío desaparece (Facturación sin Facturas ni Horas)', () => {
    const g = gruposDelMenu({ role: 'ADMIN', ocultos: ['invoices', 'timesheet'] });
    expect(g.map((x) => x.label)).not.toContain('Facturación');
  });

  it('ante la duda se muestra: null, un texto o una clave desconocida no ocultan nada', () => {
    const entero = destinos(gruposDelMenu({ role: 'ADMIN', ocultos: [] }));
    for (const raro of [null, undefined, 'accounts', ['conversaciones'], [42]]) {
      expect(destinos(gruposDelMenu({ role: 'ADMIN', ocultos: raro }))).toEqual(entero);
    }
    expect([...ocultosConocidos(['accounts', 'x'])]).toEqual(['accounts']);
  });

  it('las pantallas de Dexter no se pueden ocultar aunque llegue su ruta como clave', () => {
    const d = destinos(
      gruposDelMenu({ role: 'ADMIN', ocultos: ['conversaciones', '/conversaciones', 'agentes'] })
    );
    expect(d).toContain('/conversaciones');
    expect(d).toContain('/agentes');
  });
});

describe('qué ve cada rol', () => {
  it('Supervisor NOC: solo los roles que su servidor deja pasar', () => {
    expect(destinos(gruposDelMenu({ role: 'USER' }))).not.toContain('/supervisor-noc');
    expect(destinos(gruposDelMenu({ role: 'BODEGA' }))).not.toContain('/supervisor-noc');
    for (const r of ['ADMIN', 'SUPERVISOR', 'OPERACIONES']) {
      expect(destinos(gruposDelMenu({ role: r }))).toContain('/supervisor-noc');
    }
  });

  it('las de ADMIN no le salen a un miembro', () => {
    const d = destinos(gruposDelMenu({ role: 'USER' }));
    expect(d).not.toContain('/capacidad');
    expect(d).not.toContain('/team');
    expect(destinos(gruposDelMenu({ role: 'ADMIN' }))).toContain('/capacidad');
  });

  it('el Embudo está en Ventas', () => {
    const ventas = gruposDelMenu({ role: 'USER' }).find((g) => g.label === 'Ventas');
    expect(ventas?.items.map((i) => [i.href, i.label])).toContainEqual(['/ventas', 'Embudo']);
  });

  it('la terminología de la empresa renombra, y ocultar mira la clave, no el nombre', () => {
    const terminologia = { 'account.plural': 'Abonados' };
    const g = gruposDelMenu({ role: 'ADMIN', terminology: terminologia });
    expect(g.flatMap((x) => x.items).find((i) => i.href === '/accounts')?.label).toBe('Abonados');
    const sin = gruposDelMenu({ role: 'ADMIN', terminology: terminologia, ocultos: ['accounts'] });
    expect(destinos(sin)).not.toContain('/accounts');
  });
});
