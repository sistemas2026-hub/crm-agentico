import { describe, it, expect } from 'vitest';
import { salasDe, pisosDe } from '../departamentos.js';
import { edificioDe } from '../edificio.js';
import {
  columnasPara,
  repartirPiso,
  edificioCompacto,
  NUCLEO,
  SEPARACION,
  PASILLO
} from './distribucion.js';

/**
 * Una empresa como la del piloto: ocho departamentos y tres espacios en tres
 * pisos. Se arma con `salasDe`, que es el MISMO camino que usa la pantalla:
 * una maqueta propia probaría la maqueta.
 */
function empresaDelPiloto() {
  const dep = (id, piso, plantilla) => ({ id, rotulo: id, piso, plantilla, ocupaciones: [] });
  return {
    pisos: [
      { nivel: 3, rotulo: 'Tecnología y dirección' },
      { nivel: 2, rotulo: 'Operación y clientes' },
      { nivel: 1, rotulo: 'Administración' }
    ],
    departamentos: [
      dep('noc', 3, 'tecnica'),
      dep('campo', 2, 'operaciones'),
      dep('atencion', 2, 'atencion'),
      dep('comercial', 2, 'comercial'),
      dep('finanzas', 1, 'expedientes'),
      dep('administracion', 1, 'generica'),
      dep('rrhh', 1, 'generica'),
      dep('auditoria', 1, 'expedientes')
    ],
    espacios: [
      { id: 'direccion', rotulo: 'Dirección', piso: 3, plantilla: 'generica', ocupaciones: [] },
      { id: 'reuniones', rotulo: 'Sala de Reuniones', piso: 2, plantilla: 'reuniones', ocupaciones: [] },
      { id: 'recepcion', rotulo: 'Recepción', piso: 1, plantilla: 'generica', ocupaciones: [] }
    ]
  };
}

/** ¿Se superponen estas dos salas puestas en planta? */
function seSolapan(a, b) {
  return (
    a.x < b.x + b.ancho && b.x < a.x + a.ancho && a.y < b.y + b.fondo && b.y < a.y + a.fondo
  );
}

describe('la planta compacta reparte en varias filas', () => {
  it('ocho salas no van en una sola fila', () => {
    const { puestas } = repartirPiso(
      Array.from({ length: 8 }, () => ({ planta: { mundo: { ancho: 12, fondo: 9 } } }))
    );
    expect(Math.max(...puestas.map((p) => p.fila))).toBeGreaterThan(0);
  });

  it('ninguna sala se superpone con otra', () => {
    for (const n of [1, 2, 3, 4, 5, 8, 11, 17]) {
      const { puestas } = repartirPiso(
        Array.from({ length: n }, (_, i) => ({
          //  Tamaños desparejos a propósito: con todas iguales, una rejilla
          //  rota igual podría salir limpia por casualidad.
          planta: { mundo: { ancho: 10 + (i % 4), fondo: 8 + (i % 3) } }
        }))
      );
      for (let i = 0; i < puestas.length; i++)
        for (let j = i + 1; j < puestas.length; j++)
          expect(seSolapan(puestas[i], puestas[j]), `${n} salas: ${i} con ${j}`).toBe(false);
    }
  });

  it('ninguna sala invade el núcleo', () => {
    const { puestas } = repartirPiso(
      Array.from({ length: 9 }, () => ({ planta: { mundo: { ancho: 11, fondo: 8 } } }))
    );
    for (const p of puestas) expect(p.x).toBeGreaterThanOrEqual(NUCLEO.ancho + SEPARACION);
  });

  it('ninguna sala se sale de la huella que el piso declara', () => {
    const { puestas, huella } = repartirPiso(
      Array.from({ length: 7 }, (_, i) => ({ planta: { mundo: { ancho: 9 + i, fondo: 7 + (i % 4) } } }))
    );
    for (const p of puestas) {
      expect(p.x + p.ancho).toBeLessThanOrEqual(huella.ancho);
      expect(p.y + p.fondo).toBeLessThanOrEqual(huella.fondo);
    }
  });

  it('entre dos filas queda pasillo para circular', () => {
    const { puestas } = repartirPiso(
      Array.from({ length: 6 }, () => ({ planta: { mundo: { ancho: 10, fondo: 8 } } }))
    );
    const fila0 = puestas.filter((p) => p.fila === 0)[0];
    const fila1 = puestas.filter((p) => p.fila === 1)[0];
    expect(fila1.y - (fila0.y + fila0.fondo)).toBe(PASILLO);
  });

  it('un piso vacío sigue teniendo huella: un piso libre es un dato', () => {
    const { puestas, huella } = repartirPiso([]);
    expect(puestas).toEqual([]);
    expect(huella.ancho).toBeGreaterThan(0);
  });

  it('las columnas crecen con la cantidad y nunca bajan de dos', () => {
    expect(columnasPara(1)).toBe(1);
    expect(columnasPara(3)).toBe(2);
    expect(columnasPara(8)).toBeGreaterThanOrEqual(2);
    expect(columnasPara(20)).toBeGreaterThan(columnasPara(8));
  });
});

describe('la planta compacta contra la lineal, sobre la MISMA empresa', () => {
  const org = empresaDelPiloto();
  const salas = salasDe(org);
  const pisos = pisosDe(org, salas);

  it('el edificio deja de ser una franja: la proporción baja de 4 a menos de 2', () => {
    //  ESTE ES EL NÚMERO QUE MOTIVÓ EL SPIKE. El 31/10/2026 el diseño no se
    //  aprobó por «demasiado largo y estrecho»; esto lo mide en vez de
    //  describirlo.
    const lineal = edificioDe(salas, [], pisos).mundo;
    const compacto = edificioCompacto(pisos).huella;

    const esbeltezLineal = lineal.ancho / lineal.fondo;
    const esbeltezCompacta = compacto.ancho / compacto.fondo;

    expect(esbeltezLineal).toBeGreaterThan(4);
    expect(esbeltezCompacta).toBeLessThan(2);
    expect(esbeltezCompacta).toBeLessThan(esbeltezLineal / 2);
  });

  it('y el edificio deja de ser una torre: baja de 45 unidades de alto a 21', () => {
    //  La altura entre pisos del prototipo lineal (15) no es estética: es el
    //  mínimo que la desigualdad de oclusión permite. Aislando el piso, no
    //  hace falta.
    const lineal = edificioDe(salas, [], pisos).mundo;
    const compacto = edificioCompacto(pisos);
    expect(compacto.alto).toBeLessThan(lineal.alto / 2);
  });

  it('los tres pisos comparten huella: es un volumen, no tres bandejas', () => {
    const { niveles, huella } = edificioCompacto(pisos);
    expect(niveles).toHaveLength(3);
    for (const n of niveles)
      for (const s of n.salas) {
        expect(s.x + s.ancho).toBeLessThanOrEqual(huella.ancho);
        expect(s.y + s.fondo).toBeLessThanOrEqual(huella.fondo);
      }
  });

  it('cada sala conserva su identidad y su planta', () => {
    const { niveles } = edificioCompacto(pisos);
    const ids = niveles.flatMap((n) => n.salas.map((s) => s.sala.id)).sort();
    expect(ids).toEqual(salas.map((s) => s.id).sort());
  });
});

describe('sigue siendo configurable por empresa', () => {
  const unaSala = (id, piso) => ({ id, rotulo: id, piso, plantilla: 'generica', ocupaciones: [] });

  it('una empresa de un piso y tres departamentos', () => {
    const org = {
      pisos: [{ nivel: 1, rotulo: 'Todo' }],
      departamentos: [unaSala('a', 1), unaSala('b', 1), unaSala('c', 1)],
      espacios: []
    };
    const salas = salasDe(org);
    const { niveles, huella } = edificioCompacto(pisosDe(org, salas));
    expect(niveles).toHaveLength(1);
    expect(niveles[0].salas).toHaveLength(3);
    expect(huella.ancho).toBeGreaterThan(0);
  });

  it('una empresa de cinco pisos', () => {
    const org = {
      pisos: [1, 2, 3, 4, 5].map((n) => ({ nivel: n, rotulo: `P${n}` })),
      departamentos: [1, 2, 3, 4, 5].flatMap((n) => [unaSala(`a${n}`, n), unaSala(`b${n}`, n)]),
      espacios: []
    };
    const salas = salasDe(org);
    const { niveles } = edificioCompacto(pisosDe(org, salas));
    expect(niveles).toHaveLength(5);
    //  Cada nivel sube lo mismo y ninguno se queda a la altura de otro.
    const alturas = niveles.map((n) => n.gz).sort((a, b) => a - b);
    expect(new Set(alturas).size).toBe(5);
  });

  it('un piso declarado y vacío aparece igual', () => {
    const org = {
      pisos: [{ nivel: 2, rotulo: 'Libre' }, { nivel: 1, rotulo: 'Ocupado' }],
      departamentos: [unaSala('a', 1)],
      espacios: []
    };
    const salas = salasDe(org);
    const { niveles } = edificioCompacto(pisosDe(org, salas));
    expect(niveles.map((n) => n.nivel).sort()).toEqual([1, 2]);
    expect(niveles.find((n) => n.nivel === 2).salas).toEqual([]);
  });

  it('aislar un nivel lo baja al suelo y deja fuera a los demás', () => {
    const org = empresaDelPiloto();
    const salas = salasDe(org);
    const pisos = pisosDe(org, salas);
    const { niveles } = edificioCompacto(pisos, { soloNivel: 2 });
    expect(niveles).toHaveLength(1);
    expect(niveles[0].nivel).toBe(2);
    expect(niveles[0].gz).toBe(0);
  });

  it('cambiar el tamaño de una sala corre a las de su derecha y a nadie más', () => {
    const chica = Array.from({ length: 4 }, () => ({ planta: { mundo: { ancho: 10, fondo: 8 } } }));
    const grande = chica.map((s, i) =>
      i === 0 ? { planta: { mundo: { ancho: 18, fondo: 8 } } } : s
    );
    const a = repartirPiso(chica).puestas;
    const b = repartirPiso(grande).puestas;
    //  La de la columna siguiente se corrió; la de la fila de abajo, en su
    //  misma columna, no se movió en x.
    expect(b[1].x).toBeGreaterThan(a[1].x);
    expect(b[2].x).toBe(a[2].x);
  });
});
