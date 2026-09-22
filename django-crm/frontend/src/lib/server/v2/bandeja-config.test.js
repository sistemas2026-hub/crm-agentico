import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * El puente entre la pantalla de ajustes y el motor.
 *
 * Lo que se afirma acá es el EFECTO, no que el mecanismo exista: que `leer`
 * devuelva null en vez de tirar (si tirara, el hub de /settings se caería
 * entero y el síntoma sería "no puedo entrar a configuración"), y que `guardar`
 * mande SIEMPRE los dos valores -- omitir uno lo borraría, porque el motor
 * reemplaza el par completo.
 *
 * El módulo lee env al llamarse, no al importarse, así que un solo mock
 * mutable alcanza para los dos casos.
 */
const { envMock } = vi.hoisted(() => ({
  /** @type {Record<string, string>} */
  envMock: {}
}));
vi.mock('$env/dynamic/private', () => ({ env: envMock }));

const { leerAjustesBandeja, guardarAjustesBandeja } = await import('./bandeja-config.js');

const CONFIGURADO = {
  PRIVATE_ASISTENTE_URL: 'http://motor:5000',
  PRIVATE_ASISTENTE_TENANT: 'rapilink'
};

/* El doble de fetch se guarda acá y no se lee desde `globalThis`: tipado,
   `globalThis.fetch` es el fetch del runtime y no tiene `.mock`, así que
   afirmarlo desde ahí ensucia svelte-check con errores que no son bugs. */
let fetchMock = vi.fn();

/** El cuerpo JSON que se mandó en la última llamada a fetch. */
function cuerpoEnviado() {
  return JSON.parse(fetchMock.mock.calls[0][1].body);
}

beforeEach(() => {
  for (const k of Object.keys(envMock)) delete envMock[k];
  Object.assign(envMock, CONFIGURADO);
  fetchMock = vi.fn();
  globalThis.fetch = fetchMock;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('leerAjustesBandeja', () => {
  it('devuelve los dos valores cuando el motor contesta', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ sla_toma_minutos: 15, umbral_rx_dbm: -27 })
    });
    expect(await leerAjustesBandeja()).toEqual({ sla_toma_minutos: 15, umbral_rx_dbm: -27 });
  });

  it('manda el tenant del servidor, no uno elegido por quien pide', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    await leerAjustesBandeja();
    expect(fetchMock.mock.calls[0][0]).toContain('tenant=rapilink');
  });

  it('devuelve null --sin tirar-- si el motor responde con error', async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({}) });
    await expect(leerAjustesBandeja()).resolves.toBeNull();
  });

  it('devuelve null --sin tirar-- si el motor no contesta', async () => {
    fetchMock.mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(leerAjustesBandeja()).resolves.toBeNull();
  });

  it('devuelve null sin salir a la red cuando no hay asistente configurado', async () => {
    delete envMock.PRIVATE_ASISTENTE_URL;
    await expect(leerAjustesBandeja()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('guardarAjustesBandeja', () => {
  beforeEach(() => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ sla_toma_minutos: 15, umbral_rx_dbm: -27 })
    });
  });

  it('manda los DOS valores aunque solo cambie uno', async () => {
    await guardarAjustesBandeja({ sla_toma_minutos: 15, umbral_rx_dbm: -27 });
    const cuerpo = cuerpoEnviado();
    expect(cuerpo).toHaveProperty('sla_toma_minutos', 15);
    expect(cuerpo).toHaveProperty('umbral_rx_dbm', -27);
  });

  it('el tenant lo pone el servidor, no el llamador', async () => {
    await guardarAjustesBandeja({ sla_toma_minutos: 0, umbral_rx_dbm: null });
    expect(cuerpoEnviado().tenant).toBe('rapilink');
  });

  it('vacío en el plazo viaja como 0, que es el "sin definir" del motor', async () => {
    await guardarAjustesBandeja({ sla_toma_minutos: '', umbral_rx_dbm: -27 });
    expect(cuerpoEnviado().sla_toma_minutos).toBe(0);
  });

  it('vacío en el umbral viaja como null, no como 0 ni como ausencia', async () => {
    await guardarAjustesBandeja({ sla_toma_minutos: 15, umbral_rx_dbm: '' });
    const cuerpo = cuerpoEnviado();
    expect(cuerpo.umbral_rx_dbm).toBeNull();
    // 0 dBm es una potencia válida y distinta de "sin definir": si el vacío
    // se tradujera a 0, la Bandeja empezaría a emitir veredictos contra un
    // umbral que nadie fijó.
    expect(cuerpo.umbral_rx_dbm).not.toBe(0);
    expect('umbral_rx_dbm' in cuerpo).toBe(true);
  });

  it('un umbral de 0 dBm se manda como 0, no se confunde con vacío', async () => {
    await guardarAjustesBandeja({ sla_toma_minutos: 15, umbral_rx_dbm: 0 });
    expect(cuerpoEnviado().umbral_rx_dbm).toBe(0);
  });

  it('propaga el mensaje del motor cuando rechaza el cambio', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'El umbral tiene que estar entre -40 y 0.' })
    });
    await expect(
      guardarAjustesBandeja({ sla_toma_minutos: 15, umbral_rx_dbm: -99 })
    ).rejects.toThrow(/entre -40 y 0/);
  });

  it('tira si no hay asistente configurado, en vez de fallar en silencio', async () => {
    delete envMock.PRIVATE_ASISTENTE_TENANT;
    await expect(
      guardarAjustesBandeja({ sla_toma_minutos: 15, umbral_rx_dbm: -27 })
    ).rejects.toThrow(/no configurado/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
