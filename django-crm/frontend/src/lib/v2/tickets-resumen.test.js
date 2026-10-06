import { describe, it, expect } from 'vitest';
import { resumenPorArea, responsablesSinArea, SIN_AREA } from './tickets-resumen.js';

/**
 * EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 06/10/2026
 * ----------------------------------------------------------------
 * La pantalla mostraba «Tickets: 47 · Soporte Técnico: 25» y parecia que 22
 * tickets no tenian area. El total venia del servidor y el desglose se
 * calculaba en el navegador sobre una pagina de 25.
 *
 * Por eso el caso central de este archivo es exactamente ese: COUNT > LIMIT.
 * Se afirma sobre el EFECTO --que el desglose corresponda al conjunto
 * completo-- y no sobre de donde salieron los numeros.
 */

const AREAS = [
  { nombre: 'cartera', etiqueta: 'Cartera' },
  { nombre: 'soporte_tecnico', etiqueta: 'Soporte Técnico' },
  { nombre: 'administracion', etiqueta: 'Administración' }
];

/** El mapa persona -> area, como lo sirve el motor. */
const MAPA = {
  'p-soporte': 'soporte_tecnico',
  'p-cartera-1': 'cartera',
  'p-cartera-2': 'cartera'
};

const fila = (assigned_to, total, extra = {}) => ({
  assigned_to, total, urgentes: 0, sin_respuesta: 0, en_progreso: 0, ...extra
});

const de = (filas, nombre) => filas.find((a) => a.nombre === nombre);

describe('el caso de produccion: 47 abiertos, pagina de 25', () => {
  //  Los 47 tenian UN responsable, el mismo, con area soporte_tecnico.
  const desglose = [fila('p-soporte', 47, { urgentes: 3, sin_respuesta: 12, en_progreso: 5 })];

  it('Soporte Técnico dice 47, no 25', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, 'soporte_tecnico').total).toBe(47);
  });

  it('y las otras dos areas, 0', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, 'cartera').total).toBe(0);
    expect(de(r, 'administracion').total).toBe(0);
  });

  it('las areas suman el total: 47 = 47 + 0 + 0', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(r.reduce((t, a) => t + a.total, 0)).toBe(47);
  });

  it('no aparece "Sin área asignada" porque no hay ninguno', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, SIN_AREA)).toBeUndefined();
  });

  it('las demas metricas tambien salen del conjunto completo', () => {
    const s = de(resumenPorArea(desglose, AREAS, MAPA), 'soporte_tecnico');
    expect([s.urgentes, s.sin_respuesta, s.en_progreso]).toEqual([3, 12, 5]);
  });
});

describe('varias areas y varias paginas', () => {
  //  260 abiertos repartidos en cuatro responsables: diez paginas de 25.
  //  Ninguna pagina contiene a los cuatro, y el desglose igual tiene que dar
  //  el total -- es lo que la version anterior no podia hacer.
  const desglose = [
    fila('p-soporte', 120, { urgentes: 10 }),
    fila('p-cartera-1', 80, { urgentes: 4 }),
    fila('p-cartera-2', 40, { urgentes: 1 }),
    fila(null, 20)
  ];
  const r = resumenPorArea(desglose, AREAS, MAPA);

  it('cada area suma a TODOS sus responsables', () => {
    expect(de(r, 'soporte_tecnico').total).toBe(120);
    expect(de(r, 'cartera').total).toBe(120);   // 80 + 40
    expect(de(r, 'administracion').total).toBe(0);
  });

  it('los urgentes tambien se suman entre responsables', () => {
    expect(de(r, 'cartera').urgentes).toBe(5);  // 4 + 1
  });

  it('los sin responsable van a "Sin área asignada"', () => {
    expect(de(r, SIN_AREA).total).toBe(20);
    expect(de(r, SIN_AREA).sin_asignar).toBe(20);
  });

  it('el total del desglose es 260, no 25', () => {
    expect(r.reduce((t, a) => t + a.total, 0)).toBe(260);
  });
});

describe('responsables sin area configurada', () => {
  const desglose = [fila('p-soporte', 5), fila('p-desconocido', 7)];

  it('sus tickets caen en "Sin área", no desaparecen', () => {
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, SIN_AREA).total).toBe(7);
  });

  it('pero NO cuentan como "sin asignar": tienen responsable', () => {
    //  Son dos problemas distintos. "Nadie lo tiene" se arregla asignando;
    //  "su area no esta configurada" se arregla en /agentes. Confundirlos
    //  esconde el que hay que arreglar.
    const r = resumenPorArea(desglose, AREAS, MAPA);
    expect(de(r, SIN_AREA).sin_asignar).toBe(0);
  });

  it('y se pueden nombrar, para avisar', () => {
    expect(responsablesSinArea(desglose, MAPA)).toEqual(['p-desconocido']);
  });

  it('sin desglose no se inventa una lista', () => {
    expect(responsablesSinArea(null, MAPA)).toEqual([]);
  });
});

describe('cuando NO se pudo contar', () => {
  it('devuelve null, no un desglose en ceros', () => {
    //  El error que este modulo existe para no repetir: un cero que dice lo
    //  que no sabe. Si esto devolviera [], la pantalla mostraria "0 tickets en
    //  todas las areas" cuando lo cierto es "no se pudo contar".
    expect(resumenPorArea(null, AREAS, MAPA)).toBeNull();
    expect(resumenPorArea(undefined, AREAS, MAPA)).toBeNull();
    expect(resumenPorArea('no soy una lista', AREAS, MAPA)).toBeNull();
  });

  it('un desglose VACIO si es un cero real', () => {
    const r = resumenPorArea([], AREAS, MAPA);
    expect(r).not.toBeNull();
    expect(r.every((a) => a.total === 0)).toBe(true);
    expect(r).toHaveLength(3);   // las tres areas, sin "Sin área"
  });
});

describe('las areas del equipo se muestran aunque esten vacias', () => {
  it('un area en cero no se esconde: que este vacia es informacion', () => {
    const r = resumenPorArea([fila('p-soporte', 3)], AREAS, MAPA);
    expect(r.map((a) => a.nombre)).toEqual(
      ['cartera', 'soporte_tecnico', 'administracion']);
  });

  it('y conserva la etiqueta que vino de la configuracion', () => {
    const r = resumenPorArea([fila('p-soporte', 3)], AREAS, MAPA);
    expect(de(r, 'soporte_tecnico').etiqueta).toBe('Soporte Técnico');
  });
});

describe('un ticket con dos responsables de areas distintas', () => {
  //  El backend agrupa por responsable, asi que un caso compartido aparece en
  //  los dos. No es doble conteo: el ticket de verdad involucra a dos areas.
  //  Lo que NO puede pasar es que eso se lea como "el total es 2".
  it('cuenta en las dos areas, y el total sigue siendo del backend', () => {
    const r = resumenPorArea([fila('p-soporte', 1), fila('p-cartera-1', 1)], AREAS, MAPA);
    expect(de(r, 'soporte_tecnico').total).toBe(1);
    expect(de(r, 'cartera').total).toBe(1);
    //  La suma da 2 para UN ticket: por eso el total de la cabecera sale de
    //  'open_count' y no de sumar las areas.
    expect(r.reduce((t, a) => t + a.total, 0)).toBe(2);
  });
});
