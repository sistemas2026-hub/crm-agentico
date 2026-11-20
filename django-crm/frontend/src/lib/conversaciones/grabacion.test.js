/**
 * D29 — los recursos del compositor se sueltan al desmontar.
 *
 * Lo que se afirma acá es el EFECTO sobre el recurso (el track se detuvo, el
 * interval se canceló, no se armó adjunto), nunca que exista un `onDestroy`.
 * Una prueba que afirma que un mecanismo existe sobrevive intacta a una
 * inversión de la conducta.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  sesionDeGrabacion,
  soltarRecursosDelCompositor,
  SIN_MICROFONO
} from './grabacion.js';

/** Un track que recuerda si lo detuvieron. */
function track() {
  return { detenido: false, stop() { this.detenido = true; } };
}

/** El doble del MediaRecorder del navegador, con su máquina de estados. */
function fabricaDeGrabadores() {
  const creados = [];
  class Doble {
    constructor(stream, opciones) {
      this.stream = stream;
      this.opciones = opciones;
      this.state = 'inactive';
      this.onstop = null;
      this.ondataavailable = null;
      this.paradas = 0;
      creados.push(this);
    }
    static isTypeSupported(m) {
      return m === 'audio/ogg;codecs=opus';
    }
    start() {
      this.state = 'recording';
    }
    pause() {
      this.state = 'paused';
    }
    resume() {
      this.state = 'recording';
    }
    stop() {
      this.paradas += 1;
      if (this.state === 'inactive') throw new Error('InvalidStateError');
      this.state = 'inactive';
      this.onstop?.();
    }
    /** Lo que hace el navegador justo antes del onstop. */
    emitirAudio(bytes = 128) {
      this.ondataavailable?.({ data: new Blob([new Uint8Array(bytes)], { type: 'audio/ogg' }) });
    }
  }
  return { Doble, creados };
}

/**
 * Arma el entorno: micrófono, grabador y los avisos que la página recibiría.
 * Los dobles se instalan en `globalThis` con cast: son dobles a propósito, no
 * implementaciones completas de las interfaces del DOM.
 *
 * @param {{ permiso?: 'pendiente' }} [opciones]
 */
function escenario({ permiso } = {}) {
  const tracks = [track(), track()];
  const stream = { getTracks: () => tracks };
  const { Doble, creados } = fabricaDeGrabadores();

  /** @type {(s: any) => void} */
  let resolverPermiso = () => {};
  const pendiente = new Promise((r) => (resolverPermiso = r));
  const glob = /** @type {any} */ (globalThis);
  glob.MediaRecorder = Doble;
  glob.navigator ??= {};
  Object.defineProperty(glob.navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(() => (permiso === 'pendiente' ? pendiente : Promise.resolve(stream)))
    }
  });

  const avisos = {
    archivos: [],
    errores: [],
    estados: [],
    segundos: []
  };
  const sesion = sesionDeGrabacion({
    alArchivo: (f) => avisos.archivos.push(f),
    alFallar: (m) => avisos.errores.push(m),
    alCambiar: (e) => avisos.estados.push(e),
    alSegundo: (s) => avisos.segundos.push(s)
  });
  return {
    sesion,
    tracks,
    creados,
    avisos,
    concederPermiso: () => (resolverPermiso(stream), pendiente)
  };
}

const todosDetenidos = (tracks) => tracks.every((t) => t.detenido);

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('D29 · caso 1 — desmontar con la grabación ya activa', () => {
  it('apaga el micrófono, corta el cronómetro y NO arma adjunto', async () => {
    const { sesion, tracks, creados, avisos } = escenario();
    await sesion.iniciar();
    creados[0].emitirAudio();
    expect(todosDetenidos(tracks)).toBe(false);

    vi.advanceTimersByTime(3000);
    expect(avisos.segundos.at(-1)).toBe(3);

    sesion.soltar();

    expect(todosDetenidos(tracks)).toBe(true);
    // El cronómetro no avanza más: si el interval siguiera vivo, esto sumaría.
    const ultimo = avisos.segundos.at(-1);
    vi.advanceTimersByTime(10000);
    expect(avisos.segundos.at(-1)).toBe(ultimo);
    // Irse de la conversación no es terminar de grabar.
    expect(avisos.archivos).toHaveLength(0);
  });

  it('desarma el onstop antes de parar, así el recorder no puede armar nada', async () => {
    const { sesion, creados, avisos } = escenario();
    await sesion.iniciar();
    creados[0].emitirAudio();

    sesion.soltar();
    // Aunque el navegador dispare el evento tarde, ya no hay quién lo escuche.
    creados[0].onstop?.();
    expect(avisos.archivos).toHaveLength(0);
  });
});

describe('D29 · caso 2 — desmontar con getUserMedia todavía pendiente', () => {
  it('detiene el stream que llega tarde y no enciende nada', async () => {
    const { sesion, tracks, creados, avisos, concederPermiso } = escenario({
      permiso: 'pendiente'
    });
    const arranque = sesion.iniciar();

    // Quien atiende cambia de conversación ANTES de conceder el permiso.
    sesion.soltar();
    expect(sesion.soltada).toBe(true);

    // Y recién ahora el navegador entrega el micrófono.
    await concederPermiso();
    await arranque;

    expect(todosDetenidos(tracks)).toBe(true);
    expect(creados).toHaveLength(0); // ningún MediaRecorder nuevo
    expect(sesion.activa).toBe(false);

    // Ningún cronómetro arrancó.
    vi.advanceTimersByTime(5000);
    expect(avisos.segundos).toHaveLength(0);
    expect(avisos.estados.filter((e) => e.grabando)).toHaveLength(0);
  });
});

describe('D29 · caso 3 — object URL del adjunto', () => {
  it('revoca la URL local al soltar los recursos', () => {
    const revocadas = [];
    const sesion = { soltar: vi.fn() };
    soltarRecursosDelCompositor({
      sesion,
      adjunto: { url: 'blob:local-123' },
      revocar: (u) => revocadas.push(u)
    });
    expect(sesion.soltar).toHaveBeenCalled();
    expect(revocadas).toEqual(['blob:local-123']);
  });

  it('sin inyectar nada, llama al revokeObjectURL del navegador', () => {
    // La prueba de arriba inyecta `revocar` y por eso NO protege el camino
    // real: el que corre en producción es el valor por omisión. Si alguien lo
    // quitara, aquella seguiría verde y el blob quedaría colgado.
    const espia = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    soltarRecursosDelCompositor({
      sesion: { soltar: () => {} },
      adjunto: { url: 'blob:de-verdad' }
    });
    expect(espia).toHaveBeenCalledWith('blob:de-verdad');
  });

  it('no revoca nada cuando el adjunto no tiene URL propia', () => {
    const revocadas = [];
    // Un documento se adjunta sin previsualización: url es ''.
    soltarRecursosDelCompositor({
      sesion: { soltar: () => {} },
      adjunto: { url: '' },
      revocar: (u) => revocadas.push(u)
    });
    soltarRecursosDelCompositor({
      sesion: { soltar: () => {} },
      adjunto: null,
      revocar: (u) => revocadas.push(u)
    });
    expect(revocadas).toEqual([]);
  });
});

describe('D29 · caso 4 — el teardown es idempotente', () => {
  it('soltar dos veces no lanza ni detiene dos veces', async () => {
    const { sesion, tracks, creados } = escenario();
    await sesion.iniciar();

    sesion.soltar();
    expect(() => sesion.soltar()).not.toThrow();
    expect(todosDetenidos(tracks)).toBe(true);
    expect(creados[0].paradas).toBe(1);
  });

  it('soltar después de cancelar a mano no lanza', async () => {
    const { sesion, creados } = escenario();
    await sesion.iniciar();

    sesion.cancelar();
    expect(() => sesion.soltar()).not.toThrow();
    expect(creados[0].paradas).toBe(1);
  });

  it('soltar sin haber grabado nunca no lanza', () => {
    const { sesion } = escenario();
    expect(() => sesion.soltar()).not.toThrow();
  });
});

describe('D29 · caso 5 — la grabación normal sigue funcionando', () => {
  it('parar arma el adjunto de audio, como antes', async () => {
    const { sesion, tracks, creados, avisos } = escenario();
    await sesion.iniciar();
    expect(avisos.estados.at(-1)).toEqual({ grabando: true, pausada: false });

    creados[0].emitirAudio();
    sesion.parar();

    expect(avisos.archivos).toHaveLength(1);
    expect(avisos.archivos[0].name).toBe('nota-de-voz.ogg');
    expect(avisos.archivos[0].type).toBe('audio/ogg');
    // Y el micrófono se suelta igual al terminar.
    expect(todosDetenidos(tracks)).toBe(true);
    expect(avisos.estados.at(-1)).toEqual({ grabando: false, pausada: false });
  });

  it('pausar y reanudar no toca el micrófono ni el adjunto', async () => {
    const { sesion, tracks, creados } = escenario();
    await sesion.iniciar();

    sesion.pausar();
    expect(creados[0].state).toBe('paused');
    sesion.pausar();
    expect(creados[0].state).toBe('recording');
    expect(todosDetenidos(tracks)).toBe(false);
  });

  it('el cronómetro se congela mientras está en pausa', async () => {
    const { sesion, avisos } = escenario();
    await sesion.iniciar();

    vi.advanceTimersByTime(2000);
    expect(avisos.segundos.at(-1)).toBe(2);
    sesion.pausar();
    vi.advanceTimersByTime(5000);
    expect(avisos.segundos.at(-1)).toBe(2);
    sesion.pausar();
    vi.advanceTimersByTime(1000);
    expect(avisos.segundos.at(-1)).toBe(3);
  });

  it('un micrófono denegado avisa y no deja nada encendido', async () => {
    const { sesion, avisos, creados } = escenario();
    /** @type {any} */ (globalThis).navigator.mediaDevices.getUserMedia = vi.fn(() =>
      Promise.reject(new Error('NotAllowedError'))
    );
    await sesion.iniciar();
    expect(avisos.errores).toContain(SIN_MICROFONO);
    expect(creados).toHaveLength(0);
    expect(sesion.activa).toBe(false);
  });
});

describe('D29 · una sesión por página, nunca una global', () => {
  it('soltar una sesión no inutiliza a la otra', async () => {
    // Conversación A y conversación B. Si `soltada` viviera a nivel de módulo,
    // irse de A dejaría a B sin poder grabar nunca más -- y el síntoma sería
    // rarísimo de diagnosticar.
    // A se abre y se cierra ENTERA antes de montar B: `escenario()` instala su
    // propio getUserMedia en el global, así que solaparlos le daría a A el
    // micrófono de B y la prueba mediría otra cosa.
    const a = escenario();
    await a.sesion.iniciar();
    a.sesion.soltar();
    expect(a.sesion.soltada).toBe(true);
    expect(todosDetenidos(a.tracks)).toBe(true);

    const b = escenario();
    expect(b.sesion.soltada).toBe(false);
    await b.sesion.iniciar();
    expect(b.sesion.activa).toBe(true);
    expect(b.avisos.estados.at(-1)).toEqual({ grabando: true, pausada: false });

    // Y el micrófono de B sigue encendido pese a que el de A se apagó.
    expect(todosDetenidos(b.tracks)).toBe(false);
  });
});

describe('D29 · el módulo es seguro de importar en SSR', () => {
  it('no evalúa navigator, window ni MediaRecorder al importarse', async () => {
    const glob = /** @type {any} */ (globalThis);
    const guardado = {
      navigator: Object.getOwnPropertyDescriptor(glob, 'navigator'),
      window: Object.getOwnPropertyDescriptor(glob, 'window'),
      MediaRecorder: Object.getOwnPropertyDescriptor(glob, 'MediaRecorder')
    };
    delete glob.navigator;
    delete glob.window;
    delete glob.MediaRecorder;
    try {
      // La query fuerza una instancia nueva del módulo, sin la caché del
      // import de arriba de este archivo. Va por variable porque TypeScript no
      // modela las queries de Vite y sobre un literal las toma como parte del
      // nombre del archivo.
      const sinCache = './grabacion.js?sin-navegador';
      const recien = await import(sinCache);
      // Importar no lanzó, y la única función que consulta el navegador
      // tampoco lo hace cuando no hay ninguno.
      expect(recien.formatoDeGrabacion()).toBe('');
      expect(typeof recien.sesionDeGrabacion).toBe('function');
    } finally {
      for (const [k, d] of Object.entries(guardado)) {
        if (d) Object.defineProperty(glob, k, d);
      }
    }
  });
});

describe('D29 · caso 6 — cancelar a mano conserva su conducta', () => {
  it('apaga el micrófono, corta el cronómetro y descarta el audio', async () => {
    const { sesion, tracks, creados, avisos } = escenario();
    await sesion.iniciar();
    creados[0].emitirAudio();
    vi.advanceTimersByTime(4000);

    sesion.cancelar();

    expect(todosDetenidos(tracks)).toBe(true);
    expect(avisos.archivos).toHaveLength(0);
    expect(avisos.estados.at(-1)).toEqual({ grabando: false, pausada: false });
    const ultimo = avisos.segundos.at(-1);
    vi.advanceTimersByTime(5000);
    expect(avisos.segundos.at(-1)).toBe(ultimo);
  });

  it('deja la sesión lista para volver a grabar — a diferencia de soltar', async () => {
    const { sesion, creados } = escenario();
    await sesion.iniciar();
    sesion.cancelar();
    expect(sesion.soltada).toBe(false);

    await sesion.iniciar();
    expect(creados).toHaveLength(2);
    expect(sesion.activa).toBe(true);
  });
});
