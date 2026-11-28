/**
 * Respuestas rápidas (11/11/2026): la lógica sin DOM. Qué palabra se está
 * escribiendo, qué coincide, cómo queda el texto, y la regla que no se puede
 * romper -- con la lista abierta, Enter ELIGE y no envía.
 */
import { describe, it, expect } from 'vitest';
import {
  consultaDeBarra,
  filtrarRespuestas,
  primerNombre,
  resolverNombre,
  insertarRespuesta,
  teclaDeLaLista,
  MAXIMO_VISIBLES
} from './respuestas-rapidas.js';

const R = [
  { atajo: 'saludo', texto: 'Hola {nombre}, ¿en qué te ayudo?' },
  { atajo: 'reinicio', texto: 'Desconectá el equipo 30 segundos y volvé a conectarlo.' },
  { atajo: 'horario-sabado', texto: 'Los sábados atendemos de 8 a 12.' },
  { atajo: 'pago', texto: 'Podés pagar por Efecty o en la oficina. Atención de lunes a viernes.' }
];

describe('qué «/palabra» se está escribiendo', () => {
  it('al principio del texto', () => {
    expect(consultaDeBarra('/sal', 4)).toEqual({ desde: 0, hasta: 4, filtro: 'sal' });
  });

  it('la barra sola ya abre, con filtro vacío', () => {
    expect(consultaDeBarra('/', 1)).toEqual({ desde: 0, hasta: 1, filtro: '' });
  });

  it('después de un espacio o un salto de línea', () => {
    expect(consultaDeBarra('Buen día /rei', 13)).toEqual({ desde: 9, hasta: 13, filtro: 'rei' });
    expect(consultaDeBarra('Hola\n/ho', 8)).toEqual({ desde: 5, hasta: 8, filtro: 'ho' });
  });

  it('pegada a otra letra no abre nada: «24/7», «y/o»', () => {
    expect(consultaDeBarra('atendemos 24/7', 14)).toBeNull();
    expect(consultaDeBarra('y/o', 3)).toBeNull();
  });

  it('con el cursor fuera de la palabra no abre', () => {
    expect(consultaDeBarra('/sal y algo más', 15)).toBeNull();
  });

  it('con el cursor en el medio, filtra hasta el cursor y reemplaza la palabra entera', () => {
    expect(consultaDeBarra('/saludo gracias', 3)).toEqual({ desde: 0, hasta: 7, filtro: 'sa' });
  });

  it('una ruta («/a/b») no es un atajo', () => {
    expect(consultaDeBarra('/var/log', 8)).toBeNull();
  });
});

describe('qué respuestas coinciden', () => {
  it('sin filtro, todas en el orden guardado', () => {
    expect(filtrarRespuestas(R, '').map((r) => r.atajo)).toEqual([
      'saludo',
      'reinicio',
      'horario-sabado',
      'pago'
    ]);
  });

  it('primero las que empiezan con lo escrito, después las que lo contienen, al final por texto', () => {
    const lista = [
      { atajo: 'hora', texto: 'x' },
      { atajo: 'mi-horario', texto: 'x' },
      { atajo: 'otro', texto: 'abre a la hora de siempre' }
    ];
    expect(filtrarRespuestas(lista, 'hor').map((r) => r.atajo)).toEqual(['hora', 'mi-horario', 'otro']);
  });

  it('sin mayúsculas ni tildes que importen', () => {
    expect(filtrarRespuestas(R, 'SAL').map((r) => r.atajo)).toEqual(['saludo']);
    expect(filtrarRespuestas(R, 'sabados').map((r) => r.atajo)).toEqual(['horario-sabado']);
    expect(filtrarRespuestas(R, 'atencion').map((r) => r.atajo)).toEqual(['pago']);
  });

  it('nada que coincida es una lista vacía, no todas', () => {
    expect(filtrarRespuestas(R, 'zzz')).toEqual([]);
  });

  it('nunca más de las que se muestran a la vez', () => {
    const muchas = Array.from({ length: 20 }, (_, i) => ({ atajo: `r${i}`, texto: 't' }));
    expect(filtrarRespuestas(muchas, 'r')).toHaveLength(MAXIMO_VISIBLES);
  });

  it('sin lista, o con filas rotas, no revienta', () => {
    expect(filtrarRespuestas(/** @type {any} */ (null), 'a')).toEqual([]);
    expect(filtrarRespuestas(/** @type {any} */ ([{ atajo: 'a' }, null]), '')).toEqual([]);
  });
});

describe('{nombre}', () => {
  it('el primer nombre; uno en MAYÚSCULAS se pasa a «Ana», no se le grita', () => {
    expect(primerNombre('ANA MARÍA PÉREZ')).toBe('Ana');
    expect(primerNombre('  Carlos Gómez ')).toBe('Carlos');
    expect(primerNombre('McKenzie Ruiz')).toBe('McKenzie');
    expect(primerNombre(null)).toBe('');
    expect(primerNombre('573001234567')).toBe('');
  });

  it('con nombre, se reemplaza', () => {
    expect(resolverNombre('Hola {nombre}, ¿en qué te ayudo?', 'Ana')).toBe('Hola Ana, ¿en qué te ayudo?');
  });

  it('sin nombre, se quita sin dejar la frase rota', () => {
    expect(resolverNombre('Hola {nombre}, ¿en qué te ayudo?', '')).toBe('Hola, ¿en qué te ayudo?');
    expect(resolverNombre('¡Gracias {nombre}!', '')).toBe('¡Gracias!');
    expect(resolverNombre('{nombre}, su equipo ya volvió.', '')).toBe('Su equipo ya volvió.');
    expect(resolverNombre('Listo {nombre}. Cualquier cosa nos escribe.', '')).toBe(
      'Listo. Cualquier cosa nos escribe.'
    );
  });

  it('un texto sin {nombre} no se toca', () => {
    expect(resolverNombre('Texto  con  dobles', '')).toBe('Texto  con  dobles');
  });
});

describe('elegir una respuesta', () => {
  it('reemplaza la «/palabra» por el texto, con el nombre, y deja el cursor al final', () => {
    const texto = 'Buen día /sal';
    const r = insertarRespuesta(texto, /** @type {any} */ (consultaDeBarra(texto, 13)), R[0], 'Ana');
    expect(r.texto).toBe('Buen día Hola Ana, ¿en qué te ayudo?');
    expect(r.cursor).toBe(r.texto.length);
  });

  it('en el medio del texto conserva lo que sigue', () => {
    const texto = '/rei y avisame';
    const r = insertarRespuesta(texto, /** @type {any} */ (consultaDeBarra(texto, 4)), R[1], '');
    expect(r.texto).toBe(`${R[1].texto} y avisame`);
    expect(r.cursor).toBe(R[1].texto.length);
  });

  it('el texto insertado ya no abre la lista otra vez', () => {
    const texto = '/sal';
    const r = insertarRespuesta(texto, /** @type {any} */ (consultaDeBarra(texto, 4)), R[0], 'Ana');
    expect(consultaDeBarra(r.texto, r.cursor)).toBeNull();
  });
});

describe('las teclas con la lista abierta', () => {
  it('EL EFECTO: Enter con la lista abierta ELIGE, no envía', () => {
    expect(teclaDeLaLista({ key: 'Enter' }, true, 0, 3)).toEqual({ accion: 'elegir' });
    expect(teclaDeLaLista({ key: 'Tab' }, true, 0, 3)).toEqual({ accion: 'elegir' });
  });

  it('con la lista cerrada Enter sigue su camino (enviar)', () => {
    expect(teclaDeLaLista({ key: 'Enter' }, false, 0, 3)).toBeNull();
    expect(teclaDeLaLista({ key: 'Enter' }, true, 0, 0)).toBeNull();
  });

  it('Shift+Enter sigue siendo salto de línea', () => {
    expect(teclaDeLaLista({ key: 'Enter', shiftKey: true }, true, 0, 3)).toBeNull();
  });

  it('las flechas se mueven y dan la vuelta', () => {
    expect(teclaDeLaLista({ key: 'ArrowDown' }, true, 2, 3)).toEqual({ accion: 'mover', activa: 0 });
    expect(teclaDeLaLista({ key: 'ArrowUp' }, true, 0, 3)).toEqual({ accion: 'mover', activa: 2 });
  });

  it('Esc cierra; una letra es para escribir', () => {
    expect(teclaDeLaLista({ key: 'Escape' }, true, 0, 3)).toEqual({ accion: 'cerrar' });
    expect(teclaDeLaLista({ key: 'a' }, true, 0, 3)).toBeNull();
  });
});
