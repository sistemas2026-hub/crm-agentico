import { describe, it, expect } from 'vitest';
import { medicionDe, enlaceCaido, potenciaAtenuada } from './optica.js';

/**
 * El bug que estas pruebas existen para que no vuelva (visto en PRODUCCION el
 * 22/09/2026): el panel mostraba «TRUE» como estado de la ONU y nunca la
 * potencia óptica.
 *
 * Las dos cosas eran lo mismo: se leía `status` --que es del SOBRE de SmartOLT
 * y vale `true`-- en vez de `onu_status`, y se buscaba `signal_1310` donde la
 * API devuelve `onu_signal_1490`.
 *
 * Las respuestas de abajo son la forma REAL, con el sobre incluido, tal como
 * la entrega el motor (`consultar_estado_ont` y `consultar_senal_ont` no
 * declaran `extraer_de`).
 */
const ESTADO_REAL = {
  response_code: 'success',
  status: true,                       // <-- del SOBRE. No es el estado de la ONU.
  onu_status: 'Online',
  last_status_change: '2026-09-22 06:14:02'
};

const SENAL_REAL = {
  response_code: 'success',
  status: true,
  onu_signal: 'Very good',
  onu_signal_1310: -23.98,
  onu_signal_1490: -21.74
};

const lectura = (extra = {}) => ({
  disponible: true,
  umbral_rx_dbm: -27,
  optica: { serial: 'HWTCA6FB5263', estado: ESTADO_REAL, senal: SENAL_REAL, topologia: null, ...extra }
});

describe('medicionDe', () => {
  it('el estado sale de onu_status, NUNCA del status del sobre', () => {
    const m = medicionDe(lectura());
    expect(m.enlace).toBe('Online');
    expect(m.enlace).not.toBe(true);
    expect(m.enlace).not.toBe('true');
  });

  it('un booleano jamas se dibuja como estado, venga de donde venga', () => {
    const m = medicionDe(lectura({ estado: { response_code: 'success', status: true } }));
    // Sin onu_status no hay estado; con senal sigue habiendo medicion.
    expect(m.enlace).toBeNull();
  });

  it('la potencia sale de onu_signal_1490, la de BAJADA', () => {
    const m = medicionDe(lectura());
    expect(m.rx).toBe(-21.74);
  });

  it('no confunde la de subida con la de bajada', () => {
    const m = medicionDe(lectura());
    expect(m.rxSubida).toBe(-23.98);
    expect(m.rx).not.toBe(m.rxSubida);
  });

  it('trae la clasificacion en texto que ya hace SmartOLT', () => {
    expect(medicionDe(lectura()).clasificacion).toBe('Very good');
  });

  it('acepta tambien la forma DESENVUELTA, por si se agrega extraer_de', () => {
    const m = medicionDe({
      optica: {
        serial: 'X', estado: { onu_status: 'Offline' },
        senal: { signal_1490: -30.2, signal_1310: -25 }
      }
    });
    expect(m.enlace).toBe('Offline');
    expect(m.rx).toBe(-30.2);
  });

  it("'-' no es un numero: SmartOLT lo usa para 'no reporta'", () => {
    const m = medicionDe(lectura({ senal: { ...SENAL_REAL, onu_signal_1490: '-' } }));
    expect(m.rx).toBeNull();
  });

  it('sin estado NI potencia no hay medicion: una tarjeta vacia se lee como roto', () => {
    expect(medicionDe({ optica: { serial: 'X', estado: { status: true }, senal: { status: true } } })).toBeNull();
  });

  it('sin lectura devuelve null en vez de tirar', () => {
    expect(medicionDe(null)).toBeNull();
    expect(medicionDe({})).toBeNull();
    expect(medicionDe({ optica: null })).toBeNull();
  });
});

describe('enlaceCaido', () => {
  it('Online no esta caido; cualquier otra cosa si', () => {
    expect(enlaceCaido({ enlace: 'Online' })).toBe(false);
    expect(enlaceCaido({ enlace: 'Offline' })).toBe(true);
    expect(enlaceCaido({ enlace: 'LOS' })).toBe(true);
  });
  it('sin estado no se afirma nada', () => {
    expect(enlaceCaido({ enlace: null })).toBeNull();
    expect(enlaceCaido(null)).toBeNull();
  });
});

describe('potenciaAtenuada', () => {
  it('mas negativo que el umbral es atenuado', () => {
    expect(potenciaAtenuada({ rx: -30 }, -27)).toBe(true);
    expect(potenciaAtenuada({ rx: -21.74 }, -27)).toBe(false);
  });

  it("sin umbral NO se afirma que este bien -- 'no sabemos' no es 'esta bien'", () => {
    expect(potenciaAtenuada({ rx: -30 }, null)).toBeNull();
    expect(potenciaAtenuada({ rx: -30 }, undefined)).toBeNull();
  });

  it('sin lectura tampoco se afirma nada', () => {
    expect(potenciaAtenuada({ rx: null }, -27)).toBeNull();
    expect(potenciaAtenuada(null, -27)).toBeNull();
  });

  it('un umbral de 0 dBm es un umbral valido, no "sin definir"', () => {
    expect(potenciaAtenuada({ rx: -1 }, 0)).toBe(true);
  });
});
