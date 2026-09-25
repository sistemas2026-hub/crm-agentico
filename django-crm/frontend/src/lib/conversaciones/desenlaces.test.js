import { describe, it, expect, vi } from 'vitest';
import {
  MAX_NOTA,
  cargarDesenlaces,
  motivoParaNoCerrar,
  cuerpoDeCierre,
  categoriaVisible
} from './desenlaces.js';

/**
 * B6, del lado de la pantalla.
 *
 * Lo que se afirma acá es el EFECTO: qué se manda, qué impide mandar, qué
 * pasa cuando el catálogo no llega. No que las funciones existan.
 */

const CATALOGO = [
  { codigo: 'equipo_cliente', nombre: 'Equipo del cliente', categoria_base: 'equipo_cliente', origen: 'plataforma' },
  { codigo: 'facturacion', nombre: 'Facturación', categoria_base: 'facturacion', origen: 'plataforma' },
  { codigo: 'fibra_poste_17', nombre: 'Poste 17', categoria_base: 'red_distribucion', origen: 'tenant' }
];

describe('no se puede cerrar sin elegir', () => {
  it('sin código elegido el cierre no procede', () => {
    expect(motivoParaNoCerrar({ codigo: '', catalogo: CATALOGO })).toBeTruthy();
  });

  it('con un código del catálogo, sí', () => {
    expect(motivoParaNoCerrar({ codigo: 'facturacion', catalogo: CATALOGO })).toBe('');
  });

  it('un código que no está en el catálogo se rechaza acá, sin ir al servidor', () => {
    expect(motivoParaNoCerrar({ codigo: 'inventado', catalogo: CATALOGO })).toBeTruthy();
  });

  it('con el catálogo vacío no se ofrece cerrar, y el motivo lo dice', () => {
    const motivo = motivoParaNoCerrar({ codigo: 'facturacion', catalogo: [] });
    expect(motivo).toBeTruthy();
    expect(motivo.toLowerCase()).toContain('cierre');
  });

  it('una nota demasiado larga impide cerrar', () => {
    expect(
      motivoParaNoCerrar({ codigo: 'facturacion', nota: 'x'.repeat(MAX_NOTA + 1), catalogo: CATALOGO })
    ).toBeTruthy();
    expect(
      motivoParaNoCerrar({ codigo: 'facturacion', nota: 'x'.repeat(MAX_NOTA), catalogo: CATALOGO })
    ).toBe('');
  });

  it('cada impedimento dice algo distinto: no es un booleano disfrazado', () => {
    const motivos = new Set([
      motivoParaNoCerrar({ codigo: '', catalogo: CATALOGO }),
      motivoParaNoCerrar({ codigo: 'inventado', catalogo: CATALOGO }),
      motivoParaNoCerrar({ codigo: 'facturacion', catalogo: [] }),
      motivoParaNoCerrar({ codigo: 'facturacion', nota: 'x'.repeat(999), catalogo: CATALOGO })
    ]);
    expect(motivos.size).toBe(4);
  });
});

describe('lo que se manda', () => {
  it('lleva el código elegido y una clave de operación nueva cada vez', () => {
    const a = cuerpoDeCierre({ codigo: 'facturacion' });
    const b = cuerpoDeCierre({ codigo: 'facturacion' });
    expect(a.desenlace).toBe('facturacion');
    expect(a.clave_operacion).toBeTruthy();
    expect(a.clave_operacion).not.toBe(b.clave_operacion);
  });

  it('una nota en blanco NO viaja: "sin nota" y "nota vacía" son lo mismo', () => {
    expect(cuerpoDeCierre({ codigo: 'facturacion', nota: '   ' })).not.toHaveProperty('nota');
    expect(cuerpoDeCierre({ codigo: 'facturacion', nota: ' se resolvió por teléfono ' }).nota).toBe(
      'se resolvió por teléfono'
    );
  });

  it('no inventa un desenlace por defecto: manda vacío lo que le den vacío', () => {
    // El servidor lo rechaza con 400, y eso es lo correcto. Si esta función
    // rellenara 'otro' para evitar el error, la columna se llenaría de 'otro'
    // y nadie podría distinguir un caso sin clasificar de uno clasificado.
    expect(cuerpoDeCierre({ codigo: '' }).desenlace).toBe('');
  });
});

describe('el catálogo viene del motor', () => {
  it('lo devuelve tal cual cuando responde bien', async () => {
    const traer = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ desenlaces: CATALOGO })
    });
    const r = await cargarDesenlaces(traer);
    expect(r.desenlaces).toHaveLength(3);
    expect(r.error).toBe('');
    expect(traer).toHaveBeenCalledWith('/api/conversaciones/desenlaces');
  });

  it('si el motor falla devuelve lista vacía y el motivo, sin lanzar', async () => {
    const traer = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'Asistente no configurado' })
    });
    const r = await cargarDesenlaces(traer);
    expect(r.desenlaces).toEqual([]);
    expect(r.error).toBe('Asistente no configurado');
  });

  it('si la red se cae tampoco lanza: la pantalla que el operador está leyendo no se rompe', async () => {
    const traer = vi.fn().mockRejectedValue(new Error('offline'));
    const r = await cargarDesenlaces(traer);
    expect(r.desenlaces).toEqual([]);
    expect(r.error).toBe('offline');
  });

  it('la lista NO está escrita en el frontend', async () => {
    // Si alguien copia los doce códigos acá, el día que una empresa agregue
    // uno propio la pantalla no lo ofrece y nadie entiende por qué.
    const fuente = await import('node:fs').then((fs) =>
      fs.readFileSync(new URL('./desenlaces.js', import.meta.url), 'utf8')
    );
    const codigo = fuente
      .split('\n')
      .filter((l) => !l.trim().startsWith('*') && !l.trim().startsWith('/*'))
      .join('\n');
    for (const base of ['equipo_cliente', 'fibra_acometida', 'red_central', 'falso_positivo_ia']) {
      expect(codigo).not.toContain(base);
    }
  });
});

describe('la categoría se muestra sólo donde agrega algo', () => {
  it('un código propio muestra a qué categoría de plataforma pertenece', () => {
    expect(categoriaVisible(CATALOGO[2])).toBe('red_distribucion');
  });

  it('un código base no la repite: sería "Facturación · facturacion"', () => {
    expect(categoriaVisible(CATALOGO[1])).toBe('');
  });
});
