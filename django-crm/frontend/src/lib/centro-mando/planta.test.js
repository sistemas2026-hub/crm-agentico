import { describe, it, expect } from 'vitest';
import {
  ejes, iso, zonaDe, semillaDe, tomaDe, tono,
  cuerpoQueCabe, recortar, cambios, COLORES_AGENTE
} from './planta.js';

describe('la proyeccion', () => {
  it('a 30 grados es la isometria clasica', () => {
    const e = ejes(30);
    expect(e.ex).toBeCloseTo(0.866, 3);
    expect(e.ey).toBeCloseTo(0.5, 3);
  });

  it('subir la elevacion separa mas las filas en pantalla', () => {
    // Es la propiedad entera por la que la elevacion es un parametro: decide
    // cuanto aire hay entre una fila y la de atras.
    const bajo = iso(100, 100, 0, ejes(30))[1];
    const alto = iso(100, 100, 0, ejes(40))[1];
    expect(alto).toBeGreaterThan(bajo);
  });

  it('z sube en pantalla sin mover en planta', () => {
    const e = ejes(34);
    const [x0, y0] = iso(50, 50, 0, e);
    const [x1, y1] = iso(50, 50, 20, e);
    expect(x1).toBe(x0);
    expect(y1).toBe(y0 - 20);
  });
});

describe('las zonas', () => {
  it('el rol de entrada es la recepcion', () => {
    expect(zonaDe({ nombre: 'cliente_final', orientado_a: 'cliente_final' }, 'cliente_final')).toBe('recepcion');
  });

  it('SIN rol de entrada declarado, nadie es recepcion', () => {
    // No se adivina. Deducirlo del "primer rol orientado al cliente" es el
    // error que dejo a un suscriptor sin internet hablando con ventas.
    const a = { nombre: 'ventas', orientado_a: 'cliente_final' };
    expect(zonaDe(a, null)).toBe('cliente');
    expect(zonaDe(a, undefined)).toBe('cliente');
  });

  it('separa quien atiende al cliente de quien no', () => {
    expect(zonaDe({ nombre: 'ventas', orientado_a: 'cliente_final' }, 'otro')).toBe('cliente');
    expect(zonaDe({ nombre: 'admin', orientado_a: 'colaborador' }, 'otro')).toBe('interno');
    expect(zonaDe({ nombre: 'sin_dato' }, 'otro')).toBe('interno');
  });
});

describe('la identidad visual', () => {
  it('el mismo nombre da SIEMPRE el mismo color', () => {
    // La pantalla se repinta cada 12 s: con azar le cambiaria la cara a la
    // gente delante de quien esta mirando.
    const a = tomaDe(semillaDe('soporte_tecnico_cliente'), 23, COLORES_AGENTE);
    const b = tomaDe(semillaDe('soporte_tecnico_cliente'), 23, COLORES_AGENTE);
    expect(a).toBe(b);
  });

  it('nombres distintos reparten sobre la paleta', () => {
    const nombres = ['soporte', 'facturacion', 'ventas', 'administracion',
                     'cliente_final', 'configuracion_guiada', 'despacho', 'identidad'];
    const colores = new Set(nombres.map((n) => tomaDe(semillaDe(n), 23, COLORES_AGENTE)));
    expect(colores.size).toBeGreaterThan(3);
  });

  it('tono aclara y oscurece sin salirse del rango', () => {
    expect(tono('#000000', 1)).toBe('#ffffff');
    expect(tono('#ffffff', -1)).toBe('#000000');
    expect(tono('#4A6FA5', 0.5)).toMatch(/^#[0-9a-f]{6}$/);
  });
});

describe('el texto que tiene que caber', () => {
  it('encoge la letra hasta que el nombre entra entero', () => {
    const ancho = 60;
    const c = cuerpoQueCabe('ATENCIÓN AL CLIENTE', ancho, 7.2, 3.6);
    expect('ATENCIÓN AL CLIENTE'.length * c * 0.72).toBeLessThanOrEqual(ancho + 0.001);
  });

  it('no pasa del maximo con un nombre corto', () => {
    expect(cuerpoQueCabe('VENTAS', 300, 7.2, 3.6)).toBe(7.2);
  });

  it('no baja del minimo con un nombre absurdo', () => {
    expect(cuerpoQueCabe('A'.repeat(200), 60, 7.2, 3.6)).toBe(3.6);
  });

  it('recorta solo cuando ya no hay cuerpo que alcance', () => {
    expect(recortar('VENTAS', 100, 5)).toBe('VENTAS');
    expect(recortar('A'.repeat(200), 60, 3.6)).toContain('…');
  });

  it('las mayusculas ocupan mas que las minusculas', () => {
    // 0.62em valia para minusculas y se aplicaba tambien al nombre del area,
    // que va en MAYUSCULAS: el calculo decia que entraba y se recortaba.
    expect(cuerpoQueCabe('ABCDEFGH', 100, 99, 1, 0.72))
      .toBeLessThan(cuerpoQueCabe('ABCDEFGH', 100, 99, 1, 0.62));
  });
});

describe('que cambio entre dos fotos', () => {
  const a = (nombre, extra = {}) => ({ nombre, estado: 'idle', conversaciones: 0, ...extra });

  it('sin foto previa, todos son nuevos y nada parpadea', () => {
    const c = cambios([], [a('soporte', { estado: 'error' })]);
    expect(c.soporte.esNuevo).toBe(true);
    expect(c.soporte.entroEnAlarma).toBe(false);
  });

  it('ENTRAR en alarma es un cambio', () => {
    const c = cambios([a('soporte')], [a('soporte', { estado: 'error' })]);
    expect(c.soporte.entroEnAlarma).toBe(true);
  });

  it('SEGUIR en alarma no lo es', () => {
    // Un destello que se repite cada 12 s deja de avisar y pasa a ser ruido.
    const c = cambios([a('soporte', { estado: 'error' })], [a('soporte', { estado: 'error' })]);
    expect(c.soporte.entroEnAlarma).toBe(false);
  });

  it('guarda la carga previa para poder contar de un numero al otro', () => {
    const c = cambios([a('soporte', { conversaciones: 8 })], [a('soporte', { conversaciones: 12 })]);
    expect(c.soporte.cargaPrevia).toBe(8);
  });

  it('detecta cuando un puesto EMPIEZA a necesitar una persona', () => {
    const antes = [a('soporte', { esperando_humano: 0 })];
    const ahora = [a('soporte', { esperando_humano: 3 })];
    expect(cambios(antes, ahora).soporte.empezoAEsperar).toBe(true);
    expect(cambios(ahora, ahora).soporte.empezoAEsperar).toBe(false);
  });

  it('aguanta listas vacias o ausentes', () => {
    expect(cambios(null, null)).toEqual({});
    expect(cambios(undefined, [])).toEqual({});
  });
});
