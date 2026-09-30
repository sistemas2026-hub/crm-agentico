/**
 * NINGUN console.* DEL FRONTEND VUELCA UN OBJETO DEL DOMINIO.
 *
 * Todo lo que va a console.* se vuelve una miga de Sentry (y, con logs
 * habilitados, un log). El gancho beforeBreadcrumb limpia lo que llega, pero
 * la primera linea de defensa es no mandarlo: `console.error('...', conversacion)`
 * serializa nombre, telefono y el hilo entero.
 *
 * Dos afirmaciones:
 *   1. ningun console.* recibe como argumento un identificador que nombre un
 *      objeto del dominio (conversacion, cliente, mensaje, respuesta, payload...);
 *   2. los tres puntos centrales por donde pasan TODAS las peticiones al
 *      backend (api.js x2, api-helpers.js) registran con describirError(), no
 *      el error entero -- un error de fetch/axios carga la respuesta del
 *      backend y, en axios, las cabeceras con el JWT.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const RAIZ = path.resolve('./src');

function archivos(dir) {
  const salida = [];
  for (const nombre of readdirSync(dir)) {
    const ruta = path.join(dir, nombre);
    if (statSync(ruta).isDirectory()) salida.push(...archivos(ruta));
    else if (/\.(js|ts|svelte)$/.test(nombre) && !/\.test\.js$/.test(nombre)) salida.push(ruta);
  }
  return salida;
}

const DOMINIO = /\b(conversacion|conversation|conversaciones|cliente|customer|mensaje|mensajes|message|messages|respuesta|response|payload|body|datos|data|usuario|user|contacto)\b/;

describe('console.* sin objetos del dominio', () => {
  const ofensores = [];
  for (const ruta of archivos(RAIZ)) {
    const texto = readFileSync(ruta, 'utf8');
    const re = /console\.(error|warn|log|info|debug)\(([^;]*?)\)\s*;?/g;
    let m;
    while ((m = re.exec(texto))) {
      const args = m[2];
      // Un acceso a campo (`datos?.error`, `resp.status`) no es volcar el objeto.
      const identificadores = args.split(/[,(]/).map((s) => s.trim()).filter(Boolean);
      const malos = identificadores.filter((id) => /^[A-Za-z_$][\w$]*$/.test(id) && DOMINIO.test(id));
      if (malos.length) {
        const linea = texto.slice(0, m.index).split('\n').length;
        ofensores.push(`${path.relative(RAIZ, ruta)}:${linea} -> ${malos.join(', ')}`);
      }
    }
  }
  it('no hay ninguno', () => {
    expect(ofensores).toEqual([]);
  });
});

describe('los puntos centrales de la API registran con describirError', () => {
  for (const archivo of ['lib/api.js', 'lib/api-helpers.js']) {
    it(archivo, () => {
      const texto = readFileSync(path.join(RAIZ, archivo), 'utf8');
      expect(texto).toContain("from '$lib/observabilidad/privacidad.js'");
      expect(texto).not.toMatch(/console\.error\([^)]*,\s*error\s*\)/);
      expect(texto).toMatch(/describirError\(error\)/);
    });
  }
});
