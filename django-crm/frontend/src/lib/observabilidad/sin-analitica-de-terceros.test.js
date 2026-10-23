/**
 * NINGUNA PAGINA CARGA ANALITICA DE TERCEROS.
 *
 * app.html es la plantilla de TODAS las paginas, incluidas las publicas cuya
 * URL es la llave de acceso (/solicitud/<token>, el portal de facturas). Hasta
 * el 23/10/2026 cargaba el Google Analytics de BottleCRM, heredado al
 * vendorizar: cada URL abierta salia a una cuenta ajena. Un proveedor nuevo
 * exige resolver la autorizacion de tratamiento antes (CLAUDE.md §5).
 *
 * Se afirma sobre el archivo y no sobre un flag: si una actualizacion de
 * BottleCRM vuelve a traer el tag, esto se pone rojo.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const plantilla = readFileSync(path.resolve('./src/app.html'), 'utf8');

const PROVEEDORES = [
  'googletagmanager.com',
  'google-analytics.com',
  'gtag(',
  'connect.facebook.net',
  'static.hotjar.com',
  'cdn.segment.com',
  'plausible.io',
  'clarity.ms'
];

describe('app.html no carga analitica de terceros', () => {
  for (const marca of PROVEEDORES) {
    it(`no aparece ${marca}`, () => {
      expect(plantilla).not.toContain(marca);
    });
  }

  it('declara el idioma de la interfaz', () => {
    expect(plantilla).toContain('<html lang="es">');
  });
});
