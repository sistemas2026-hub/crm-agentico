import { describe, expect, it } from 'vitest';

import { desdeHace, filasDeSeguimiento, horaCorta, ZONA } from './relojes-del-mapa.js';

/**
 * LOS DOS RELOJES DEL MAPA (05/11/2026).
 *
 * Lo que de verdad se prueba acá no es formatear una hora: es que la pantalla
 * pueda distinguir «la pantalla dejó de preguntar» de «ese teléfono dejó de
 * reportar». Son dos fallos distintos, llevan a llamar a dos personas
 * distintas, y con un solo número se ven iguales.
 */
describe('la hora, en la zona de la operación', () => {
  it('no usa la zona del equipo que mira: la fija en Bogotá', () => {
    //  ESTA PRUEBA ESTUVO EN FALSO VERDE Y SE MIDIÓ (05/11/2026). Decía lo
    //  mismo que dice ahora, pero el runner corre en America/Bogota: quitarle
    //  el `timeZone` a la función daba EXACTAMENTE el mismo resultado y la
    //  prueba seguía pasando. La mutación sobrevivió.
    //
    //  Por eso acá se finge otro equipo. Node reevalúa la zona cuando cambia
    //  `process.env.TZ` --comprobado en este entorno-- así que esto mide el
    //  caso real: el supervisor que abre la pantalla desde un portátil con el
    //  reloj en otra zona, y compara esa hora contra su celular para decidir
    //  si llama a alguien.
    expect(ZONA).toBe('America/Bogota');
    const previa = process.env.TZ;
    try {
      process.env.TZ = 'Asia/Tokyo';
      //  Sin la zona fija esto daría 01:20 (Tokio) y el supervisor leería
      //  que su técnico reportó de madrugada.
      expect(horaCorta('2026-10-31T16:20:00Z')).toBe('11:20');
      expect(horaCorta('2026-10-31T11:20:00-05:00')).toBe('11:20');
      //  Y el caso DISCRIMINA: si el instante diera la misma hora en las dos
      //  zonas, las dos líneas de arriba pasarían con y sin el arreglo.
      expect(
        new Date('2026-10-31T16:20:00Z').toLocaleTimeString('es-CO', {
          hour: '2-digit', minute: '2-digit', hour12: false
        })
      ).not.toBe('11:20');
    } finally {
      if (previa === undefined) delete process.env.TZ;
      else process.env.TZ = previa;
    }
  });

  it('en 24 horas, porque la operación no dice a. m.', () => {
    expect(horaCorta('2026-10-31T19:05:00-05:00')).toBe('19:05');
  });

  it('con segundos cuando se piden: la verificación corre cada 15 s', () => {
    //  Sin segundos, dos verificaciones seguidas muestran la misma hora y el
    //  supervisor no puede ver que la pantalla sigue viva.
    expect(horaCorta('2026-10-31T11:20:07-05:00', true)).toBe('11:20:07');
  });

  it('lo que no es una fecha sale vacío, nunca «Invalid Date»', () => {
    for (const malo of [null, undefined, '', 'ayer', NaN]) {
      expect(horaCorta(malo)).toBe('');
    }
  });
});

describe('hace cuánto', () => {
  it('segundos mientras sean segundos', () => {
    expect(desdeHace(0)).toBe('hace 0 s');
    expect(desdeHace(8)).toBe('hace 8 s');
    expect(desdeHace(59)).toBe('hace 59 s');
  });

  it('redondea HACIA ABAJO: decir de más es lo peligroso', () => {
    //  119 s es «hace 1 min», no «hace 2 min». Exagerar el atraso hace que el
    //  supervisor crea que la pantalla está peor de lo que está y salga a
    //  buscar un fallo que no existe.
    expect(desdeHace(60)).toBe('hace 1 min');
    expect(desdeHace(119)).toBe('hace 1 min');
    expect(desdeHace(120)).toBe('hace 2 min');
  });

  it('pasada la hora lo dice en horas y minutos', () => {
    expect(desdeHace(3600)).toBe('hace 1 h 0 min');
    expect(desdeHace(5400)).toBe('hace 1 h 30 min');
  });

  it('un número negativo o basura no imprime basura', () => {
    expect(desdeHace(-10)).toBe('hace 0 s');
    // @ts-expect-error a propósito: llega de la red
    expect(desdeHace('x')).toBe('hace 0 s');
  });
});

const conPos = (extra = {}) => ({
  jornada: 'j-1',
  cuadrilla: 'Cuadrilla #5',
  posicion: {
    latitud: 10.9185, longitud: -74.7668, minutos: 2, fresca: true,
    medida_en: '2026-10-31T11:20:00-05:00', de: 'Mario Vásquez'
  },
  ...extra
});

describe('las filas de abajo del mapa', () => {
  it('la que NO reportó también sale: si no, desaparece de la pantalla', () => {
    //  LA MITAD DEL VALOR DE ESTA LISTA. Una cuadrilla sin señal no tiene pin
    //  --no se le inventa uno-- así que esta fila es el único lugar donde el
    //  supervisor la ve. Sin ella, nadie echa de menos lo que no ve.
    const filas = filasDeSeguimiento([
      conPos(),
      { jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null }
    ]);

    expect(filas.length).toBe(2);
    expect(filas[1].cuadrilla).toBe('Cuadrilla #3');
    expect(filas[1].dice).toBe('sin señal');
  });

  it('la fila sin posición NO es centrable, y eso se puede ver', () => {
    //  Un botón que no responde al clic, sin explicación, se lee como
    //  pantalla rota. El componente lo deshabilita con esto.
    const [a, b] = filasDeSeguimiento([
      conPos(),
      { jornada: 'j-2', cuadrilla: 'Cuadrilla #3', posicion: null }
    ]);

    expect(a.centrable).toBe(true);
    expect(b.centrable).toBe(false);
  });

  it('dice la HORA del reporte y hace cuánto, no una sola de las dos', () => {
    //  La hora sola no se compara con nada de un vistazo; «hace 2 min» solo
    //  no sirve para un reclamo posterior. Las dos juntas sí.
    const [f] = filasDeSeguimiento([conPos()]);

    expect(f.dice).toContain('11:20');
    expect(f.dice).toContain('hace 2 min');
    expect(f.hora).toBe('11:20');
  });

  it('lo viejo se marca viejo, igual que el pin', () => {
    const [f] = filasDeSeguimiento([
      conPos({ posicion: { ...conPos().posicion, minutos: 45, fresca: false } })
    ]);

    expect(f.fresca).toBe(false);
    expect(f.dice).toContain('hace 45 min');
  });

  it('sin cuadrillas, sin filas, y sin reventar', () => {
    expect(filasDeSeguimiento([])).toEqual([]);
    expect(filasDeSeguimiento(undefined)).toEqual([]);
    expect(filasDeSeguimiento(null)).toEqual([]);
  });
});
