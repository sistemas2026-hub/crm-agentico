import { describe, it, expect } from 'vitest';
import {
  COLORES,
  NOMBRES_DE_COLOR,
  estiloDeColor,
  etiquetasDeFila,
  recortar,
  contarEtiquetas
} from './etiquetas.js';

/**
 * Las etiquetas del equipo (11/11/2026): la paleta cerrada, el cruce de las
 * claves de la fila con el catálogo, y los conteos del filtro.
 */
const catalogo = [
  { clave: 'vip', nombre: 'Cliente VIP', color: 'violeta' },
  { clave: 'moroso', nombre: 'Moroso', color: 'rojo' },
  { clave: 'visita', nombre: 'Pide visita', color: 'azul' }
];

describe('la paleta', () => {
  it('son los mismos ocho nombres que valida el esquema del motor', () => {
    // nucleo/config/schema.py::COLORES_DE_ETIQUETA, en el mismo orden.
    expect(NOMBRES_DE_COLOR).toEqual([
      'gris', 'rojo', 'naranja', 'amarillo', 'verde', 'azul', 'violeta', 'rosa'
    ]);
  });

  it('el estilo sale de la paleta, y un color desconocido cae en gris', () => {
    expect(estiloDeColor('rojo')).toContain(COLORES.rojo.texto);
    expect(estiloDeColor('#ff00aa;background:url(x)')).toBe(estiloDeColor('gris'));
  });
});

describe('las etiquetas de una fila', () => {
  it('en el orden del catálogo, con nombre y color, sin las que no existen', () => {
    const e = etiquetasDeFila(['visita', 'borrada', 'vip'], catalogo);
    expect(e.map((x) => x.clave)).toEqual(['vip', 'visita']);
    expect(e[0].nombre).toBe('Cliente VIP');
  });

  it('dos a la vista y «+N» con el resto', () => {
    expect(recortar([1, 2, 3, 4])).toEqual({ visibles: [1, 2], resto: 2 });
    expect(recortar([1, 2])).toEqual({ visibles: [1, 2], resto: 0 });
  });
});

describe('el filtro por etiqueta', () => {
  const filas = [
    { id: 'a', etiquetas_del_equipo: ['vip'] },
    { id: 'b', etiquetas_del_equipo: ['vip', 'moroso'] },
    { id: 'c' }
  ];

  it('cuenta las filas de cada una, y no ofrece las que no tienen ninguna', () => {
    const n = contarEtiquetas(filas, catalogo).map(([e, k]) => [e.clave, k]);
    expect(n).toEqual([['vip', 2], ['moroso', 1]]);
  });

  it('la elegida se queda aunque cuente 0: tiene que haber dónde tocar para sacarla', () => {
    const n = contarEtiquetas(filas, catalogo, 'visita').map(([e, k]) => [e.clave, k]);
    expect(n).toContainEqual(['visita', 0]);
  });
});
