import { describe, it, expect } from 'vitest';
import {
  PREFIJO_SESION,
  claveDeSesion,
  aBurbujas,
  esDuplicado,
  bloqueDeContexto,
  mensajeParaElMotor
} from './chat-sesion.js';

describe('claveDeSesion — de quien es la conversacion', () => {
  it('lleva prefijo, para no compartir hilo con el asistente general', () => {
    expect(claveDeSesion({ id: 'u-1' })).toBe('snoc:u-1');
  });

  it('NO es el user.id pelado: ese es el que usa /api/asistente', () => {
    //  Si esto fallara, las dos pantallas escribirian en la misma
    //  conversacion del motor y una pregunta sobre facturacion aparecería
    //  dentro del chat del Supervisor.
    expect(claveDeSesion({ id: 'u-1' })).not.toBe('u-1');
  });

  it('dos usuarios distintos no comparten clave', () => {
    expect(claveDeSesion({ id: 'u-1' })).not.toBe(claveDeSesion({ id: 'u-2' }));
  });

  it('sin usuario devuelve vacio, no una clave por defecto', () => {
    //  Una clave inventada haria que dos personas sin sesion compartieran
    //  hilo. Quien llama tiene que cortar.
    expect(claveDeSesion(null)).toBe('');
    expect(claveDeSesion(undefined)).toBe('');
    expect(claveDeSesion({})).toBe('');
    expect(claveDeSesion({ id: '' })).toBe('');
  });

  it('acepta un id numerico', () => {
    expect(claveDeSesion({ id: 7 })).toBe('snoc:7');
  });

  it('el id 0 es un id valido, no una ausencia', () => {
    expect(claveDeSesion({ id: 0 })).toBe(`${PREFIJO_SESION}0`);
  });
});

describe('aBurbujas — el hilo que vuelve del motor', () => {
  const crudo = [
    { id: 'm1', rol: 'user', contenido: '¿Que deberia revisar primero?', creado_en: '2026-10-05T10:00:00' },
    { id: 'm2', rol: 'assistant', contenido: 'Hay 3 casos sin movimiento.', creado_en: '2026-10-05T10:00:09' }
  ];

  it('traduce los roles del motor a quien escribio', () => {
    const b = aBurbujas(crudo);
    expect(b.map((x) => x.rol)).toEqual(['usuario', 'supervisor']);
  });

  it('conserva el orden del hilo', () => {
    expect(aBurbujas(crudo)[0].texto).toContain('revisar primero');
  });

  it('descarta system y tool: son andamiaje, no mensajes', () => {
    const b = aBurbujas([...crudo, { id: 'm3', rol: 'system', contenido: 'nota interna' },
                         { id: 'm4', rol: 'tool', contenido: '{"ok":true}' }]);
    expect(b).toHaveLength(2);
    expect(JSON.stringify(b)).not.toContain('nota interna');
  });

  it('descarta un turno con respuesta vacia (una escalada, una pausa)', () => {
    const b = aBurbujas([...crudo, { id: 'm5', rol: 'assistant', contenido: '   ' }]);
    expect(b).toHaveLength(2);
  });

  it('no explota con una respuesta inesperada', () => {
    expect(aBurbujas(null)).toEqual([]);
    expect(aBurbujas(undefined)).toEqual([]);
    expect(aBurbujas('no soy una lista')).toEqual([]);
    expect(aBurbujas([{}])).toEqual([]);
  });

  it('cada burbuja tiene id: {#each} con clave necesita uno estable', () => {
    for (const b of aBurbujas(crudo)) expect(b.id).toBeTruthy();
  });
});

describe('esDuplicado — el doble envio accidental', () => {
  const hilo = [
    { rol: 'usuario', texto: '¿Que paso con el ticket 92392?' },
    { rol: 'supervisor', texto: 'Sigue abierto.' },
    { rol: 'usuario', texto: '¿Y por que?' }
  ];

  it('mientras hay un envio en curso, repetir el ultimo es duplicado', () => {
    expect(esDuplicado('¿Y por que?', hilo, true)).toBe(true);
  });

  it('con el envio terminado, preguntar lo mismo otra vez es legitimo', () => {
    //  Una persona puede repetir una pregunta a proposito. Bloquearlo seria
    //  decidir por ella.
    expect(esDuplicado('¿Y por que?', hilo, false)).toBe(false);
  });

  it('un texto distinto no es duplicado aunque haya envio en curso', () => {
    expect(esDuplicado('otra cosa', hilo, true)).toBe(false);
  });

  it('ignora espacios al comparar', () => {
    expect(esDuplicado('  ¿Y por que?  ', hilo, true)).toBe(true);
  });

  it('un mensaje vacio nunca se manda', () => {
    expect(esDuplicado('   ', hilo, true)).toBe(true);
  });

  it('compara contra el ultimo del USUARIO, no contra el ultimo del hilo', () => {
    const conRespuesta = [...hilo, { rol: 'supervisor', texto: 'Porque nadie lo movio.' }];
    expect(esDuplicado('¿Y por que?', conRespuesta, true)).toBe(true);
  });

  it('con el hilo vacio no hay nada que duplicar', () => {
    expect(esDuplicado('hola', [], true)).toBe(false);
  });
});

describe('bloqueDeContexto — lo que esta pantalla sabe y el motor no', () => {
  it('nombra las propuestas sin revisar', () => {
    const b = bloqueDeContexto({ abiertas: 7, criticas: 2 });
    expect(b).toContain('sin revisar: 7');
    expect(b).toContain('prioridad alta: 2');
  });

  it('un cero se informa: no es lo mismo que no saber', () => {
    expect(bloqueDeContexto({ abiertas: 0 })).toContain('sin revisar: 0');
  });

  it('sin datos devuelve vacio, NO un encabezado con ceros', () => {
    //  El bug que esto evita: afirmarle al modelo que no hay nada pendiente
    //  cuando lo que pasa es que el CRM no contesto.
    expect(bloqueDeContexto(null)).toBe('');
    expect(bloqueDeContexto({})).toBe('');
    expect(bloqueDeContexto({ indicadores: {} })).toBe('');
  });

  it('marca donde termina el contexto y empieza la persona', () => {
    const b = bloqueDeContexto({ abiertas: 1 });
    expect(b).toContain('[Estado del Supervisor NOC');
    expect(b).toContain('lo escribio el responsable de operaciones');
  });

  it('solo deja pasar numeros y textos de los indicadores', () => {
    const b = bloqueDeContexto({ indicadores: { sla_vencidos: 3, raro: { a: 1 }, lista: [1, 2] } });
    expect(b).toContain('sla_vencidos: 3');
    expect(b).not.toContain('raro');
    expect(b).not.toContain('lista');
  });
});

describe('mensajeParaElMotor', () => {
  it('pone el contexto antes de la pregunta', () => {
    const m = mensajeParaElMotor('¿que reviso?', '[Estado]\n- x: 1');
    expect(m.indexOf('[Estado]')).toBeLessThan(m.indexOf('¿que reviso?'));
  });

  it('sin contexto manda la pregunta sola, sin envoltorio', () => {
    expect(mensajeParaElMotor('  ¿que reviso?  ', '')).toBe('¿que reviso?');
  });
});
