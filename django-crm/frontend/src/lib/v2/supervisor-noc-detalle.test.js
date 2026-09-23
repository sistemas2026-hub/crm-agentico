import { describe, it, expect } from 'vitest';
import {
  comunDeEvidencia,
  fuentesDeEvidencia,
  baseDePrioridad,
  contrasteDeEstados,
  haceCuanto,
  expiraEn,
  antiguedadDelCaso,
  lecturaExterna,
  CONTEXTO_AUSENTE
} from '$lib/v2/supervisor-noc-detalle.js';

/** La evidencia real de un 'caso_desincronizado', tal como la manda el backend. */
const EVIDENCIA = [
  { fuente: 'caso', id: '6c489ae4', dato: 'abierto desde 2026-09-15 (7 dias)', observado_en: '2026-09-22T16:39:00Z' },
  { fuente: 'caso', id: '6c489ae4', dato: 'estado actual: New', observado_en: '2026-09-22T16:39:00Z' },
  { fuente: 'caso', id: '6c489ae4', dato: 'estado en el proveedor: Cerrado', observado_en: '2026-09-22T16:39:00Z' },
  {
    fuente: 'caso',
    id: '6c489ae4',
    dato: 'estado externo leido el 2026-09-22 14:53 UTC',
    observado_en: '2026-09-22T16:39:00Z'
  },
  {
    fuente: 'calculo_prioridad',
    id: '6c489ae4',
    dato: 'base 30',
    observado_en: '2026-09-22T16:39:00Z'
  }
];

describe('comunDeEvidencia', () => {
  it('detecta el id y la hora repetidos en todas las observaciones', () => {
    const r = comunDeEvidencia(EVIDENCIA);

    expect(r?.id).toBe('6c489ae4');
    expect(r?.leido).toBe('2026-09-22T16:39:00Z');
    // La fuente NO es comun: una observacion viene de 'calculo_prioridad'.
    expect(r?.fuente).toBeNull();
  });

  it('con una sola observacion no hay nada que agrupar', () => {
    expect(comunDeEvidencia([EVIDENCIA[0]])).toBeNull();
  });

  it('si nada se repite, no agrupa', () => {
    const r = comunDeEvidencia([
      { fuente: 'a', id: '1', dato: 'x', observado_en: 'T1' },
      { fuente: 'b', id: '2', dato: 'y', observado_en: 'T2' }
    ]);

    expect(r).toBeNull();
  });

  it('no revienta con evidencia ausente', () => {
    expect(comunDeEvidencia(null)).toBeNull();
    expect(comunDeEvidencia(undefined)).toBeNull();
  });
});

describe('fuentesDeEvidencia', () => {
  it('devuelve las fuentes distintas, sin repetir', () => {
    expect(fuentesDeEvidencia(EVIDENCIA)).toEqual(['caso', 'calculo_prioridad']);
  });

  it('sin evidencia devuelve una lista vacia, no null', () => {
    expect(fuentesDeEvidencia(null)).toEqual([]);
  });
});

describe('baseDePrioridad', () => {
  it('encuentra el calculo que explica el numero', () => {
    expect(baseDePrioridad(EVIDENCIA)).toBe('base 30');
  });

  it('si el backend no lo manda, devuelve null y la vista no lo muestra', () => {
    expect(baseDePrioridad([EVIDENCIA[0]])).toBeNull();
  });
});

describe('contrasteDeEstados', () => {
  it('extrae los dos estados que SON el hallazgo', () => {
    const r = contrasteDeEstados(EVIDENCIA);

    expect(r).toEqual({ crm: 'New', proveedor: 'Cerrado' });
  });

  it('si falta uno de los dos, no muestra nada', () => {
    // Prefiere no dibujarse a dibujar medio contraste.
    const soloCrm = EVIDENCIA.filter((e) => !e.dato.startsWith('estado en el proveedor'));

    expect(contrasteDeEstados(soloCrm)).toBeNull();
  });

  it('una señal de otro tipo no produce un contraste inventado', () => {
    const otra = [{ fuente: 'orden', id: '1', dato: 'sin programacion registrada' }];

    expect(contrasteDeEstados(otra)).toBeNull();
  });

  it('tolera espacios y mayusculas en la etiqueta', () => {
    const r = contrasteDeEstados([
      { fuente: 'caso', dato: 'Estado actual : Abierto' },
      { fuente: 'caso', dato: 'ESTADO EN EL PROVEEDOR: Resuelto' }
    ]);

    expect(r).toEqual({ crm: 'Abierto', proveedor: 'Resuelto' });
  });

  it('conserva los dos puntos que vengan dentro del valor', () => {
    const r = contrasteDeEstados([
      { fuente: 'caso', dato: 'estado actual: En espera: cliente' },
      { fuente: 'caso', dato: 'estado en el proveedor: Cerrado' }
    ]);

    expect(r?.crm).toBe('En espera: cliente');
  });
});

describe('haceCuanto', () => {
  const ahora = new Date('2026-09-22T20:00:00Z').getTime();

  it('minutos, horas y dias segun la distancia', () => {
    expect(haceCuanto('2026-09-22T19:30:00Z', ahora)).toBe('hace 30 min');
    expect(haceCuanto('2026-09-22T15:00:00Z', ahora)).toBe('hace 5 h');
    expect(haceCuanto('2026-09-15T20:00:00Z', ahora)).toBe('hace 7 días');
  });

  it('una fecha futura no se dice como "hace -5 min"', () => {
    expect(haceCuanto('2026-09-22T20:30:00Z', ahora)).toBe('recién');
  });

  it('sin fecha, una raya', () => {
    expect(haceCuanto(null)).toBe('—');
    expect(haceCuanto('no es fecha')).toBe('—');
  });
});

describe('expiraEn', () => {
  const ahora = new Date('2026-09-22T20:00:00Z').getTime();

  it('dice cuanto queda, no la fecha', () => {
    expect(expiraEn('2026-09-23T08:00:00Z', ahora)).toBe('en 12 h');
    expect(expiraEn('2026-09-29T20:00:00Z', ahora)).toBe('en 7 días');
  });

  it('una propuesta pasada de fecha se declara vencida', () => {
    expect(expiraEn('2026-09-21T20:00:00Z', ahora)).toBe('vencida');
  });

  it('sin fecha, una raya', () => {
    expect(expiraEn(null)).toBe('—');
  });
});

describe('antiguedadDelCaso', () => {
  it('lee la fecha y los dias de la observacion real', () => {
    expect(antiguedadDelCaso(EVIDENCIA)).toEqual({ desde: '2026-09-15', dias: 7 });
  });

  it('si el texto no trae fecha, no inventa una', () => {
    expect(antiguedadDelCaso([{ fuente: 'caso', dato: 'abierto desde hace mucho' }])).toBeNull();
  });

  it('acepta la fecha sin el conteo de dias', () => {
    const r = antiguedadDelCaso([{ fuente: 'caso', dato: 'abierto desde 2026-09-01' }]);

    expect(r).toEqual({ desde: '2026-09-01', dias: null });
  });

  it('otra señal no produce una antiguedad inventada', () => {
    expect(antiguedadDelCaso([{ fuente: 'orden', dato: 'sin programacion' }])).toBeNull();
    expect(antiguedadDelCaso(null)).toBeNull();
  });
});

describe('lecturaExterna', () => {
  it('extrae cuando se consulto al proveedor', () => {
    expect(lecturaExterna(EVIDENCIA)).toBe('2026-09-22 14:53 UTC');
  });

  it('sin esa observacion, devuelve null y el bloque no se dibuja', () => {
    expect(lecturaExterna([EVIDENCIA[0]])).toBeNull();
    expect(lecturaExterna(undefined)).toBeNull();
  });
});

describe('CONTEXTO_AUSENTE', () => {
  it('nombra los cuatro datos que el serializer no entrega', () => {
    // Si alguno empieza a llegar, se saca de aqui y la pantalla lo muestra:
    // la lista es el unico lugar donde vive esa decision.
    expect(CONTEXTO_AUSENTE).toContain('SLA del caso');
    expect(CONTEXTO_AUSENTE).toContain('Última actividad registrada');
    expect(CONTEXTO_AUSENTE).toContain('Último compromiso pendiente');
    expect(CONTEXTO_AUSENTE).toContain('Responsable actual');
    expect(CONTEXTO_AUSENTE).toHaveLength(4);
  });
});
