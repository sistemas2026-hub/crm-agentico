import { describe, it, expect } from 'vitest';
import { efectosDeAceptar, celdaDistinta } from './supervisor-noc-ficha.js';
import { siAcepto, AUSENTE } from './supervisor-noc-detalle.js';

describe('efectosDeAceptar', () => {
  it('un cierre controlado: qué hace y que no toca WispHub', () => {
    const e = efectosDeAceptar({ ejecuta: true, pasaADespacho: false });
    expect(e.si.join(' ')).toMatch(/valida/i);
    expect(e.si.join(' ')).toMatch(/cierra el caso en Dexter/);
    expect(e.no).toContain('No toca WispHub.');
  });

  it('pasar a Despacho: NO crea la orden ni manda a nadie, NO cierra el caso', () => {
    //  El malentendido más caro: creer que aceptar ya despachó una cuadrilla.
    const e = efectosDeAceptar({ ejecuta: false, pasaADespacho: true });
    expect(e.si.join(' ')).toMatch(/Despacho/);
    expect(e.no).toContain('No crea la orden ni manda a nadie todavía.');
    expect(e.no).toContain('No cierra el caso.');
    expect(e.no).toContain('No toca WispHub.');
  });

  it('una observación: solo queda registrado, y no ejecuta nada', () => {
    const e = efectosDeAceptar({ ejecuta: false, pasaADespacho: false });
    expect(e.si).toEqual(['Queda registrado que estás de acuerdo.']);
    expect(e.no).toContain('No ejecuta ninguna acción.');
  });

  it('las tres ramas son las mismas que decide siAcepto, no otra regla', () => {
    //  Si siAcepto dice que ejecuta, la lista tiene que hablar de cerrar; si
    //  dice que pasa a Despacho, de Despacho. Se prueba con las propuestas
    //  reales que siAcepto clasifica, no con banderas inventadas.
    const desinc = siAcepto({ tipo_senal: 'caso_desincronizado', estado: 'propuesta', evidencia: [] });
    const nada = siAcepto({ tipo_senal: 'orden_sin_programar', estado: 'propuesta', evidencia: [] });
    expect(efectosDeAceptar(desinc).si.join(' ')).toMatch(desinc.ejecuta ? /cierra/ : /registrado|Despacho/);
    expect(efectosDeAceptar(nada).no.length).toBeGreaterThan(0);
  });

  it('sin datos no promete nada', () => {
    expect(efectosDeAceptar(null)).toEqual({ si: [], no: [] });
  });
});

describe('celdaDistinta', () => {
  it('marca solo cuando los dos lados tienen dato y no coinciden', () => {
    expect(celdaDistinta({ dexter: 'Abierto', wisphub: 'Cerrado' })).toBe(true);
    expect(celdaDistinta({ dexter: 'Abierto', wisphub: 'Abierto' })).toBe(false);
  });

  it('un lado sin dato NO es una diferencia: es un hueco', () => {
    //  Pintar de rojo "Sin asignar" contra "No disponible" acusaría una
    //  discrepancia que nadie midió.
    expect(celdaDistinta({ dexter: 'Sin asignar', wisphub: AUSENTE })).toBe(false);
    expect(celdaDistinta({ dexter: AUSENTE, wisphub: 'x' })).toBe(false);
    expect(celdaDistinta({ dexter: '', wisphub: 'x' })).toBe(false);
  });

  it('no distingue por mayúsculas ni espacios', () => {
    expect(celdaDistinta({ dexter: ' abierto', wisphub: 'Abierto ' })).toBe(false);
  });
});
