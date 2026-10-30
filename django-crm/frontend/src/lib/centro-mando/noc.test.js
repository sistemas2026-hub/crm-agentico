import { describe, it, expect } from 'vitest';
import { DEPARTAMENTO_NOC, puestosDelNoc, supervisorDelNoc } from './noc.js';

/**
 * QUIÉN SE SIENTA EN EL PUESTO, Y QUÉ PASA CUANDO NADIE.
 *
 * El dato que varía por empresa es el agente, y llega como parámetro desde el
 * inventario del motor. Lo que se prueba acá es que no se adivine: ni el nombre,
 * ni el área. Sentar a un agente de otra área para que la sala no se vea sosa es
 * la clase de afirmación que esta pantalla no puede hacer.
 */

describe('la sala tiene cuatro puestos y uno es el principal', () => {
  const puestos = puestosDelNoc({ nombre: 'supervisor_noc', rotulo: 'Supervisor NOC' });

  it('cuatro puestos', () => {
    expect(puestos).toHaveLength(4);
  });

  it('solo uno es principal', () => {
    expect(puestos.filter((p) => p.principal)).toHaveLength(1);
  });

  it('los identificadores no se repiten', () => {
    // Dos puestos con el mismo identificador: la selección marcaría los dos y
    // la ficha mostraría el primero. Es el tipo de defecto que se ve como «la
    // ficha muestra el puesto equivocado».
    expect(new Set(puestos.map((p) => p.id)).size).toBe(4);
  });

  it('ningún puesto se solapa con otro', () => {
    // Dos escritorios en la misma celda se dibujan uno dentro del otro, y el
    // síntoma es «el mobiliario parpadea».
    for (const a of puestos) {
      for (const b of puestos) {
        if (a === b) continue;
        const anchoA = a.principal ? 3.2 : 2.3;
        const solapaX = a.gx < b.gx + (b.principal ? 3.2 : 2.3) && a.gx + anchoA > b.gx;
        const solapaY = Math.abs(a.gy - b.gy) < 1.2;
        expect(solapaX && solapaY, `${a.id} se solapa con ${b.id}`).toBe(false);
      }
    }
  });

  it('todos caben dentro del recinto', () => {
    for (const p of puestos) {
      expect(p.gx).toBeGreaterThanOrEqual(0);
      expect(p.gx + (p.principal ? 3.2 : 2.3)).toBeLessThanOrEqual(14);
      // Una celda por delante para el personaje y una por detrás para el paso.
      expect(p.gy).toBeGreaterThanOrEqual(1);
      expect(p.gy + 1).toBeLessThanOrEqual(10);
    }
  });
});

describe('el puesto principal', () => {
  it('lleva el agente que se le pasó', () => {
    const [principal] = puestosDelNoc({ nombre: 'supervisor_noc', rotulo: 'Supervisor NOC' });
    expect(principal.agente).toBe('supervisor_noc');
    expect(principal.nombre).toBe('Supervisor NOC');
    expect(principal.area).toBe(DEPARTAMENTO_NOC.rotulo);
  });

  it('sin agente se dibuja VACÍO y lo dice', () => {
    const [principal] = puestosDelNoc(null);
    expect(principal.agente).toBeNull();
    expect(principal.area).toContain('sin agente');
  });

  it('las tres estaciones están vacías, y es la verdad', () => {
    // Hoy existe un solo agente ejecutable con puesto propio en esta área.
    // Dibujar tres ocupantes más haría una escena más vistosa y una pantalla
    // que miente sobre la plantilla.
    const [, ...estaciones] = puestosDelNoc({ nombre: 'supervisor_noc' });
    expect(estaciones.every((e) => e.agente === null)).toBe(true);
  });
});

describe('a quién elige del inventario', () => {
  const inventario = [
    { nombre: 'ventas', area: 'ventas', cargo: 'Comercial' },
    { nombre: 'supervisor_noc', area: 'operativo', cargo: 'Supervisor NOC' },
    { nombre: 'cartera', area: 'cartera', cargo: 'Cartera' }
  ];

  it('elige por área, no por nombre', () => {
    // Buscar `supervisor_noc` literal funcionaría hoy y dejaría la sala vacía
    // en la siguiente empresa, sin un error que lo explique.
    const s = supervisorDelNoc(inventario);
    expect(s.nombre).toBe('supervisor_noc');
  });

  it('acepta el rótulo además del identificador', () => {
    // Hay DOS vocabularios de área y no coinciden: la configuración declara
    // `operativo` y el campo `area` de cada rol es texto libre.
    const s = supervisorDelNoc([{ nombre: 'otro', area: 'NOC y Redes', cargo: 'Jefe de red' }]);
    expect(s.nombre).toBe('otro');
  });

  it('no adivina sinónimos', () => {
    // Aceptar «operaciones» como `operativo` serviría hoy y el día que una
    // empresa tenga las dos cosas sentaría al agente equivocado en el puesto.
    expect(supervisorDelNoc([{ nombre: 'x', area: 'operaciones' }])).toBeNull();
    expect(supervisorDelNoc([{ nombre: 'x', area: 'soporte_tecnico' }])).toBeNull();
  });

  it('sin nadie del área devuelve null', () => {
    expect(supervisorDelNoc([{ nombre: 'ventas', area: 'ventas' }])).toBeNull();
    expect(supervisorDelNoc([])).toBeNull();
    expect(supervisorDelNoc(null)).toBeNull();
  });

  it('con varios, el orden es estable', () => {
    // Un orden estable es lo que hace que la sala se vea igual en dos cargas
    // seguidas.
    const varios = [
      { nombre: 'zeta', area: 'operativo' },
      { nombre: 'alfa', area: 'operativo' }
    ];
    expect(supervisorDelNoc(varios).nombre).toBe('alfa');
    expect(supervisorDelNoc([...varios].reverse()).nombre).toBe('alfa');
  });

  it('no reordena el arreglo que recibe', () => {
    // `sort` muta. Si mutara el inventario del `load`, el resto de la pantalla
    // vería los agentes en otro orden sin motivo.
    const original = [
      { nombre: 'zeta', area: 'operativo' },
      { nombre: 'alfa', area: 'operativo' }
    ];
    supervisorDelNoc(original);
    expect(original[0].nombre).toBe('zeta');
  });
});

describe('el identificador del departamento no se renombra', () => {
  it('sigue siendo el histórico', () => {
    // Renombrarlo daría un rótulo bonito y perdería la continuidad de todo lo
    // registrado con el nombre viejo.
    expect(DEPARTAMENTO_NOC.id).toBe('operativo');
    expect(DEPARTAMENTO_NOC.rotulo).toBe('NOC y Redes');
  });
});
