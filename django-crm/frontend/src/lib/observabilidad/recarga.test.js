/**
 * LA PESTAÑA VIEJA SE RECUPERA SOLA, Y NO ENTRA EN BUCLE.
 *
 * Se afirma sobre el EFECTO: que ante el error real que produjo un deploy
 * --los mensajes literales de Chrome, Firefox, Safari y Vite-- se llame a
 * reload; que la segunda vez seguida NO se llame; y que un error cualquiera
 * no dispare nada.
 *
 * El bucle importa tanto como la recarga: si el chunk falta por otro motivo
 * (servidor sirviendo mal, red cortada), recargar sin freno deja la pagina
 * parpadeando y al operador sin poder leer el error.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  CLAVE_RECARGA,
  PATRON_CHUNK_VIEJO,
  VENTANA_MS,
  esChunkViejo,
  recargarUnaVez,
  vigilarChunksViejos
} from './recarga.js';

/** Los mensajes REALES, no una aproximacion. Los dos primeros son los que
 *  aparecieron en la consola del operador el 23/09/2026. */
const REALES = [
  'Failed to fetch dynamically imported module: https://agent.example/_app/immutable/nodes/61.CyPCFAsf.js',
  'TypeError: Failed to fetch dynamically imported module: https://agent.example/_app/immutable/nodes/65.wkkelUoO.js',
  'error loading dynamically imported module',
  'Importing a module script failed.',
  'Unable to preload CSS for /_app/immutable/assets/supervisor-noc.CN5-zGzK.css'
];

/** Lo que NO tiene que disparar una recarga. */
const AJENOS = [
  'Uncaught Error: Extension context invalidated.',
  'A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received',
  'HTTP 500: Internal Server Error',
  'TypeError: no se pudo leer la propiedad x de undefined',
  'NetworkError when attempting to fetch resource.'
];

function almacenFalso(inicial = {}) {
  const datos = { ...inicial };
  return {
    getItem: (k) => (k in datos ? datos[k] : null),
    setItem: (k, v) => {
      datos[k] = String(v);
    },
    datos
  };
}

describe('esChunkViejo', () => {
  for (const mensaje of REALES) {
    it(`reconoce: ${mensaje.slice(0, 52)}…`, () => {
      expect(esChunkViejo(new Error(mensaje))).toBe(true);
      expect(esChunkViejo(mensaje)).toBe(true);
    });
  }
  for (const mensaje of AJENOS) {
    it(`no confunde: ${mensaje.slice(0, 46)}…`, () => {
      expect(esChunkViejo(new Error(mensaje))).toBe(false);
    });
  }
  it('lee el motivo de una promesa rechazada', () => {
    expect(esChunkViejo({ reason: new Error(REALES[0]) })).toBe(true);
  });
  it('no rompe con lo que falte', () => {
    for (const v of [null, undefined, 0, '', {}, { message: null }]) {
      expect(esChunkViejo(v), String(v)).toBe(false);
    }
  });
  it('el patron no depende de mayusculas', () => {
    expect(PATRON_CHUNK_VIEJO.test('FAILED TO FETCH DYNAMICALLY IMPORTED MODULE')).toBe(true);
  });
});

describe('recargarUnaVez', () => {
  it('recarga la primera vez y deja la marca', () => {
    const almacen = almacenFalso();
    const recargar = vi.fn();
    expect(recargarUnaVez({ almacen, recargar, ahora: 1_000_000 })).toBe(true);
    expect(recargar).toHaveBeenCalledTimes(1);
    expect(almacen.getItem(CLAVE_RECARGA)).toBe('1000000');
  });

  it('NO recarga la segunda vez dentro de la ventana: eso seria un bucle', () => {
    const almacen = almacenFalso({ [CLAVE_RECARGA]: '1000000' });
    const recargar = vi.fn();
    expect(recargarUnaVez({ almacen, recargar, ahora: 1_000_000 + VENTANA_MS - 1 })).toBe(false);
    expect(recargar).not.toHaveBeenCalled();
  });

  it('vuelve a recargar pasada la ventana: es otro deploy, no el mismo', () => {
    const almacen = almacenFalso({ [CLAVE_RECARGA]: '1000000' });
    const recargar = vi.fn();
    expect(recargarUnaVez({ almacen, recargar, ahora: 1_000_000 + VENTANA_MS + 1 })).toBe(true);
    expect(recargar).toHaveBeenCalledTimes(1);
  });

  it('sin almacen no recarga: sin marca no hay como evitar el bucle', () => {
    const recargar = vi.fn();
    expect(recargarUnaVez({ almacen: null, recargar, ahora: 1 })).toBe(false);
    expect(recargar).not.toHaveBeenCalled();
  });

  it('si el almacen tira (pestaña privada, cookies bloqueadas) no rompe ni recarga', () => {
    const recargar = vi.fn();
    const almacen = {
      getItem: () => {
        throw new Error('SecurityError');
      },
      setItem: () => {}
    };
    expect(recargarUnaVez({ almacen, recargar, ahora: 1 })).toBe(false);
    expect(recargar).not.toHaveBeenCalled();
  });

  it('una marca corrupta no bloquea la recarga', () => {
    const almacen = almacenFalso({ [CLAVE_RECARGA]: 'basura' });
    const recargar = vi.fn();
    expect(recargarUnaVez({ almacen, recargar, ahora: 5_000 })).toBe(true);
  });
});

describe('vigilarChunksViejos', () => {
  function ventanaFalsa() {
    const oyentes = {};
    return {
      addEventListener: (nombre, fn) => {
        (oyentes[nombre] ??= []).push(fn);
      },
      disparar: (nombre, evento) => (oyentes[nombre] || []).forEach((fn) => fn(evento)),
      oyentes
    };
  }

  it('engancha los dos caminos por donde llega el error', () => {
    const ventana = ventanaFalsa();
    expect(vigilarChunksViejos(ventana)).toBe(true);
    expect(Object.keys(ventana.oyentes).sort()).toEqual(['unhandledrejection', 'vite:preloadError']);
  });

  it('fuera del navegador no hace nada', () => {
    expect(vigilarChunksViejos(undefined)).toBe(false);
    expect(vigilarChunksViejos({})).toBe(false);
  });

  it('una promesa rechazada por un chunk viejo se reconoce', () => {
    const ventana = ventanaFalsa();
    vigilarChunksViejos(ventana);
    // El efecto real (reload) depende del sessionStorage del navegador; aqui
    // se afirma que el camino existe y que el motivo se clasifica bien, que es
    // lo que esta prueba puede ver sin un DOM.
    expect(esChunkViejo({ reason: new Error(REALES[0]) })).toBe(true);
    expect(() => ventana.disparar('unhandledrejection', { reason: new Error('otra cosa') })).not.toThrow();
  });
});
