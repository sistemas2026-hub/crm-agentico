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
  CONTEXTO_AUSENTE,
  pasosDelCiclo,
  AUSENTE,
  nombreHumano,
  quePasa,
  prioridadHumana,
  identificacion,
  comparacionFuentes,
  analisisSeparado,
  siAcepto
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

describe('pasosDelCiclo', () => {
  const estados = (/** @type {string} */ e) =>
    Object.fromEntries(pasosDelCiclo(e).map((p) => [p.clave, p.estado]));

  it('una propuesta sin revisar esta en la primera etapa', () => {
    const r = estados('propuesta');

    expect(r.propuesta).toBe('actual');
    expect(r.revisada).toBe('inactivo');
  });

  it('una rechazada quedo revisada, pero nunca aprobada', () => {
    const r = estados('rechazada');

    expect(r.propuesta).toBe('hecho');
    expect(r.revisada).toBe('actual');
    expect(r.aprobada).toBe('inactivo');
  });

  it('una aceptada llega a aprobada y ni un paso mas', () => {
    const r = estados('aceptada');

    expect(r.aprobada).toBe('actual');
    // Aceptar significa "el Jefe esta de acuerdo", no "se hizo".
    expect(r.encolada).toBe('inactivo');
    expect(r.ejecutada).toBe('inactivo');
    expect(r.validada).toBe('inactivo');
  });

  it('las tres etapas de ejecucion NUNCA se activan, con ningun estado', () => {
    // No hay camino de ejecucion en esta etapa: si alguna se encendiera, la
    // pantalla estaria afirmando algo que el modelo no puede representar.
    for (const e of ['propuesta', 'aceptada', 'modificada', 'rechazada', 'cancelada', 'expirada']) {
      const r = estados(e);
      expect(r.encolada).toBe('inactivo');
      expect(r.ejecutada).toBe('inactivo');
      expect(r.validada).toBe('inactivo');
    }
  });

  it('siempre son seis pasos, en orden', () => {
    const claves = pasosDelCiclo('propuesta').map((p) => p.clave);

    expect(claves).toEqual(['propuesta', 'revisada', 'aprobada', 'encolada', 'ejecutada', 'validada']);
  });
});

// ===========================================================================
//  LA LECTURA HUMANA DEL HALLAZGO
// ===========================================================================
//  Estas pruebas guardan una sola cosa, y es la que la pantalla puede romper
//  sin que nadie lo note: que un dato ausente se DIGA, y que la sección
//  «¿qué pasa si acepto?» no prometa una ejecución que el sistema no hace.
//
//  El caso de referencia es real, copiado de producción el 25/09/2026:
//  ticket 92751, caso abierto en Dexter (New) y cerrado en WispHub.

const DESINCRONIZADO = {
  id: 'p-1',
  tipo_senal: 'caso_desincronizado',
  tipo_senal_display: 'Caso cerrado en el proveedor y abierto en el CRM',
  origen_tipo: 'case',
  origen_id: 'feee6eb7-4714-40c7-bc90-624bf2baf7d1',
  estado: 'propuesta',
  prioridad: 30,
  nivel_autonomia_requerido: 0,
  accion_propuesta: 'Revisar la sincronización con el proveedor: el caso figura cerrado allá y abierto en el CRM',
  motivo: 'El proveedor lo reporta como «Cerrado» y en el CRM sigue sin fecha de resolución.',
  impacto: 'Infla la cola del CRM y los conteos dejan de describir la operación.',
  evidencia: [
    { fuente: 'caso', id: 'c', dato: 'abierto desde 2026-09-15 (7 dias)', observado_en: '2026-09-22T20:34:18Z' },
    { fuente: 'caso', id: 'c', dato: 'estado actual: New', observado_en: '2026-09-22T20:34:18Z' },
    { fuente: 'caso', id: 'c', dato: 'estado en el proveedor: Cerrado', observado_en: '2026-09-22T20:34:18Z' },
    { fuente: 'caso', id: 'c', dato: 'estado externo leido el 2026-09-22 14:53 UTC', observado_en: '2026-09-22T20:34:18Z' },
    { fuente: 'calculo_prioridad', id: 'c', dato: 'base 30', observado_en: '2026-09-22T20:34:18Z' }
  ]
};

const CONTEXTO = { ticket_externo: '92751', proveedor_externo: 'wisphub', tecnico: '', zona: '' };

describe('nombre humano de la señal', () => {
  it('traduce la clave técnica a lo que el usuario reconoce', () => {
    expect(nombreHumano(DESINCRONIZADO)).toBe('Desincronización WispHub ↔ Dexter');
  });

  it('un tipo sin rótulo propio cae en lo que el backend ya traduce', () => {
    const otro = { tipo_senal: 'algo_nuevo', tipo_senal_display: 'Algo nuevo' };
    expect(nombreHumano(otro)).toBe('Algo nuevo');
  });

  it('sin propuesta, lo dice', () => {
    expect(nombreHumano(null)).toBe(AUSENTE);
  });
});

describe('¿qué está pasando?', () => {
  it('nombra los dos estados REALES, no unos supuestos', () => {
    const f = quePasa(DESINCRONIZADO);
    expect(f).toContain('Cerrado');
    expect(f).toContain('New');
  });

  it('un tipo sin frase propia usa el motivo del Supervisor', () => {
    const otro = { tipo_senal: 'x', motivo: 'Lo que el Supervisor escribió' };
    expect(quePasa(otro)).toBe('Lo que el Supervisor escribió');
  });
});

describe('prioridad humana', () => {
  it('nivel 0 (observar) es baja, aunque el número sea alto', () => {
    //  El número NO decide solo: 30 con nivel 0 es observar, no urgencia.
    const p = prioridadHumana(DESINCRONIZADO);
    expect(p.texto).toBe('Baja');
    expect(p.n).toBe(30);
  });

  it('distingue alta y media dentro del rango real medido (30-42)', () => {
    expect(prioridadHumana({ prioridad: 42, nivel_autonomia_requerido: 1 }).texto).toBe('Alta');
    expect(prioridadHumana({ prioridad: 40, nivel_autonomia_requerido: 1 }).texto).toBe('Media');
    expect(prioridadHumana({ prioridad: 30, nivel_autonomia_requerido: 1 }).texto).toBe('Baja');
  });

  it('sin prioridad no inventa una', () => {
    expect(prioridadHumana({}).texto).toBe(AUSENTE);
  });
});

describe('identificación', () => {
  it('trae el ticket del contexto de la fila, sin pedir nada más', () => {
    const filas = identificacion(DESINCRONIZADO, CONTEXTO);
    expect(filas.find((f) => f.rotulo === 'Ticket WispHub').valor).toBe('92751');
  });

  it('el caso enlaza a su ficha', () => {
    const caso = identificacion(DESINCRONIZADO, CONTEXTO).find((f) => f.rotulo === 'Caso Dexter');
    expect(caso.valor).toBe('CS-feee6eb7');
    expect(caso.href).toBe(`/tickets/${DESINCRONIZADO.origen_id}`);
  });

  it('cliente y asunto DICEN que no están, en vez de quedarse vacíos', () => {
    //  Medido: los 237 casos de producción no tienen cuenta asociada.
    const filas = identificacion(DESINCRONIZADO, CONTEXTO);
    expect(filas.find((f) => f.rotulo === 'Cliente').valor).toBe(AUSENTE);
    expect(filas.find((f) => f.rotulo === 'Asunto del ticket').valor).toBe(AUSENTE);
  });

  it('sin contexto no se cae, y declara las cuatro', () => {
    const filas = identificacion(DESINCRONIZADO);
    expect(filas).toHaveLength(4);
    expect(filas.filter((f) => f.valor === AUSENTE).length).toBe(3);
  });
});

describe('comparación Dexter ↔ WispHub', () => {
  it('pone cada estado en su columna', () => {
    const estado = comparacionFuentes(DESINCRONIZADO, CONTEXTO).find((f) => f.campo === 'Estado');
    expect(estado.dexter).toBe('New');
    expect(estado.wisphub).toBe('Cerrado');
  });

  it('no rellena una celda por simetría', () => {
    const resp = comparacionFuentes(DESINCRONIZADO, CONTEXTO).find((f) => f.campo === 'Responsable');
    expect(resp.dexter).toBe(AUSENTE);
    expect(resp.wisphub).toBe(AUSENTE);
  });

  it('la fila del proveedor habla de LECTURA, no de cambio', () => {
    //  De WispHub solo se sabe cuándo se leyó, no cuándo cambió allá.
    const filas = comparacionFuentes(DESINCRONIZADO, CONTEXTO);
    expect(filas.some((f) => f.campo === 'Última lectura')).toBe(true);
    expect(filas.some((f) => /actualizaci[oó]n/i.test(f.campo))).toBe(false);
  });

  it('con una propuesta vacía devuelve las cuatro filas, todas declaradas', () => {
    const filas = comparacionFuentes({}, {});
    expect(filas).toHaveLength(4);
    expect(filas.every((f) => f.dexter === AUSENTE && f.wisphub === AUSENTE)).toBe(true);
  });
});

describe('análisis separado', () => {
  it('separa hechos de interpretación', () => {
    const a = analisisSeparado(DESINCRONIZADO);
    expect(a.hechos.map((h) => h.dato)).toContain('estado en el proveedor: Cerrado');
    expect(a.interpretacion).toBe(DESINCRONIZADO.motivo);
    expect(a.impacto).toBe(DESINCRONIZADO.impacto);
  });

  it('el cálculo de prioridad no es un hecho observado', () => {
    const a = analisisSeparado(DESINCRONIZADO);
    expect(a.hechos.map((h) => h.dato)).not.toContain('base 30');
  });

  it('recoge lo que la evidencia declara como faltante', () => {
    const conFalta = {
      ...DESINCRONIZADO,
      evidencia: [{ fuente: 'caso', dato: 'falta el estado externo: no se pudo leer', observado_en: null }]
    };
    expect(analisisSeparado(conFalta).faltantes).toHaveLength(1);
  });

  it('sin evidencia no inventa hechos', () => {
    expect(analisisSeparado({}).hechos).toEqual([]);
  });
});

describe('¿qué pasa si acepto?', () => {
  it('NO promete que el caso se cierre', () => {
    //  La garantía más importante de esta pantalla: aceptar registra un
    //  acuerdo, no ejecuta nada. El estado «ejecutada» no existe en el modelo.
    const r = siAcepto(DESINCRONIZADO);
    expect(r.efecto).toMatch(/no cierra el caso/i);
    expect(r.efecto).toMatch(/no ejecuta/i);
    expect(JSON.stringify(r)).not.toMatch(/Dexter: ?Cerrado/);
  });

  it('muestra la acción con las palabras de la propuesta', () => {
    expect(siAcepto(DESINCRONIZADO).accion).toBe(DESINCRONIZADO.accion_propuesta);
  });

  it('dice de dónde viene la decisión y que exige confirmación humana', () => {
    const r = siAcepto(DESINCRONIZADO);
    expect(r.origenDecision).toBe('WispHub');
    expect(r.requiereConfirmacion).toBe(true);
  });

  it('sin evidencia externa no atribuye el origen a nadie', () => {
    expect(siAcepto({ accion_propuesta: 'x' }).origenDecision).toBe(AUSENTE);
  });
});
