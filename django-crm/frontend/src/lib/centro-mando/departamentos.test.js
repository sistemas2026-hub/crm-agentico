import { describe, it, expect } from 'vitest';
import { DEPARTAMENTOS, agentesDe, departamentoPorId, plantaDe, plantaDeLaEmpresa } from './departamentos.js';
import { TIPOS_DE_MUEBLE } from './escena/oficina';

/**
 * LA PLANTA ES UN DATO, Y ESTO LO MIDE.
 *
 * La prueba que de verdad importa no es que el segundo departamento se vea
 * bien: es que **no haya hecho falta tocar `escena/`**. Si un día alguien
 * resuelve una sala nueva agregando una función a la escena en vez de una fila
 * acá, lo que se pierde no es elegancia — es que el tercer departamento vuelva
 * a costar lo que costó el primero.
 *
 * Y las comprobaciones de geometría existen porque sus fallos NO dan error:
 * dos escritorios en la misma celda se dibujan uno dentro del otro y el síntoma
 * se describe como «el mobiliario parpadea».
 */

//  Los nueve roles reales del tenant, con el area que DECLARAN.
const inventario = [
  { nombre: 'supervisor_noc', area: 'Operaciones', cargo: 'Supervisor NOC' },
  { nombre: 'soporte', area: 'Atención al Cliente', cargo: 'Soporte' },
  { nombre: 'cliente_final', area: 'Atención al Cliente', cargo: 'Primera línea' },
  { nombre: 'soporte_tecnico_cliente', area: 'Soporte Técnico', cargo: 'Diagnóstico' },
  { nombre: 'facturacion', area: 'Facturación', cargo: 'Facturación' },
  { nombre: 'facturacion_cliente', area: 'Facturación', cargo: 'Cobranza' },
  { nombre: 'ventas', area: 'Ventas', cargo: 'Comercial' },
  { nombre: 'administracion', area: 'Administración', cargo: 'Administración' },
  { nombre: 'configuracion_guiada', area: 'Administración', cargo: 'Gestión' }
];

describe('hay más de un departamento, y no son el mismo con otro rótulo', () => {
  it('son al menos dos', () => {
    expect(DEPARTAMENTOS.length).toBeGreaterThanOrEqual(2);
  });

  it('los identificadores no se repiten', () => {
    expect(new Set(DEPARTAMENTOS.map((d) => d.id)).size).toBe(DEPARTAMENTOS.length);
  });

  it('cada sala tiene su propia geometría', () => {
    // Si dos salas compartieran mundo y mobiliario, la oficina virtual no
    // estaría representando a la empresa: estaría repitiendo un fondo.
    const firmas = DEPARTAMENTOS.map((d) =>
      JSON.stringify([d.planta.mundo, d.planta.mobiliario.map((m) => m.tipo).sort()])
    );
    expect(new Set(firmas).size).toBe(DEPARTAMENTOS.length);
  });

  it('la sala de atención NO tiene mobiliario de centro de operaciones', () => {
    const atencion = departamentoPorId('atencion_cliente');
    const tipos = atencion.planta.mobiliario.map((m) => m.tipo);
    expect(tipos).not.toContain('armario');
    expect(tipos).not.toContain('panel_fibra');
  });

  it('y la del NOC sí', () => {
    const tipos = departamentoPorId('operativo').planta.mobiliario.map((m) => m.tipo);
    expect(tipos).toContain('armario');
    expect(tipos).toContain('panel_fibra');
  });
});

describe('la escena sabe dibujar todo lo que las plantas piden', () => {
  it('ningún mueble declarado es de un tipo desconocido', () => {
    // Un tipo que la escena no conoce se ignora y se cuenta — no se dibuja
    // «algo parecido». Esto lo caza antes de que la sala salga incompleta.
    for (const d of DEPARTAMENTOS) {
      for (const m of d.planta.mobiliario) {
        expect(TIPOS_DE_MUEBLE, `${d.id}: ${m.tipo}`).toContain(m.tipo);
      }
    }
  });
});

describe('la geometría de cada sala cierra', () => {
  for (const d of DEPARTAMENTOS) {
    const ancho = (p) => (p.principal ? 3.2 : 2.3);

    it(`${d.id}: los puestos caben dentro del recinto`, () => {
      for (const p of d.planta.puestos) {
        expect(p.gx, p.id).toBeGreaterThanOrEqual(0);
        expect(p.gx + ancho(p), p.id).toBeLessThanOrEqual(d.planta.mundo.ancho);
        // Una celda por delante para el personaje y una por detrás para el paso.
        expect(p.gy, p.id).toBeGreaterThanOrEqual(1);
        expect(p.gy + 1, p.id).toBeLessThanOrEqual(d.planta.mundo.fondo);
      }
    });

    it(`${d.id}: ningún puesto se solapa con otro`, () => {
      for (const a of d.planta.puestos) {
        for (const b of d.planta.puestos) {
          if (a === b) continue;
          const solapaX = a.gx < b.gx + ancho(b) && a.gx + ancho(a) > b.gx;
          const solapaY = Math.abs(a.gy - b.gy) < 1.2;
          expect(solapaX && solapaY, `${a.id} con ${b.id}`).toBe(false);
        }
      }
    });

    it(`${d.id}: los identificadores de puesto no se repiten`, () => {
      // Dos con el mismo id: la selección marcaría los dos y la ficha mostraría
      // el primero. Se ve como «la ficha muestra el puesto equivocado».
      const ids = d.planta.puestos.map((p) => p.id);
      expect(new Set(ids).size).toBe(ids.length);
    });

    it(`${d.id}: el pasillo está dentro del recinto y no tiene ancho cero`, () => {
      if (!d.planta.pasillo) return;
      expect(d.planta.pasillo.desde).toBeGreaterThanOrEqual(0);
      expect(d.planta.pasillo.hasta).toBeLessThanOrEqual(d.planta.mundo.ancho);
      expect(d.planta.pasillo.hasta).toBeGreaterThan(d.planta.pasillo.desde);
    });

    it(`${d.id}: hay exactamente un puesto principal`, () => {
      expect(d.planta.puestos.filter((p) => p.principal)).toHaveLength(1);
    });
  }
});

describe('los identificadores de puesto no chocan entre salas', () => {
  it('ninguno se repite en toda la empresa', () => {
    // La selección se guarda por id. Si dos salas compartieran uno, cambiar de
    // sala dejaría marcado un puesto que no es el que se eligió.
    const todos = DEPARTAMENTOS.flatMap((d) => d.planta.puestos.map((p) => p.id));
    expect(new Set(todos).size).toBe(todos.length);
  });
});

describe('quién ocupa cada sala', () => {
  it('los agentes salen por área, no por nombre', () => {
    // Buscar `supervisor_noc` literal funcionaría hoy y dejaría la sala vacía
    // en la siguiente empresa, sin un error que lo explique.
    const atencion = agentesDe(inventario, departamentoPorId('atencion_cliente'));
    expect(atencion.map((a) => a.nombre)).toEqual(['cliente_final', 'soporte']);
  });

  it('acepta el rótulo además del identificador', () => {
    // Hay DOS vocabularios de área y no coinciden.
    const otros = agentesDe([{ nombre: 'x', area: 'NOC y Redes' }],
                            departamentoPorId('operativo'));
    expect(otros).toHaveLength(1);
  });

  it('acepta las etiquetas que el departamento DECLARA', () => {
    // `supervisor_noc` declara área «Operaciones» y el área configurada se
    // llama `operativo`: los dos vocabularios no coinciden. Antes de declarar
    // las etiquetas, esta sala salía VACÍA en producción.
    expect(agentesDe([{ nombre: 'x', area: 'Operaciones' }],
                     departamentoPorId('operativo'))).toHaveLength(1);
  });

  it('y NO adivina las que no declara', () => {
    // Aceptar parecidos serviría hoy y el día que una empresa tenga las dos
    // cosas sentaría al agente equivocado en el puesto, sin un error que lo
    // explique. Lo que acepta se escribe; no se deduce.
    for (const inventada of ['ops', 'operacion', 'red', 'noc']) {
      expect(agentesDe([{ nombre: 'x', area: inventada }],
                       departamentoPorId('operativo')), inventada).toEqual([]);
    }
  });

  it('cada área real del tenant cae en algún departamento', () => {
    // Las seis que los roles declaran hoy. Si una no cayera en ninguna sala,
    // ese agente no se dibujaría en ninguna parte y nadie se enteraría.
    const reales = ['Operaciones', 'Atención al Cliente', 'Soporte Técnico',
                    'Facturación', 'Ventas', 'Administración'];
    for (const area of reales) {
      const encaja = DEPARTAMENTOS.some(
        (d) => agentesDe([{ nombre: 'x', area }], d).length === 1
      );
      expect(encaja, `«${area}» no tiene sala`).toBe(true);
    }
  });

  it('y ninguna cae en DOS departamentos a la vez', () => {
    // El mismo agente en dos salas sería el mismo trabajo contado dos veces.
    const reales = ['Operaciones', 'Atención al Cliente', 'Soporte Técnico',
                    'Facturación', 'Ventas', 'Administración'];
    for (const area of reales) {
      const cuantas = DEPARTAMENTOS.filter(
        (d) => agentesDe([{ nombre: 'x', area }], d).length === 1
      ).length;
      expect(cuantas, `«${area}» cae en ${cuantas} salas`).toBe(1);
    }
  });

  it('no muta el inventario que recibe', () => {
    // `sort` muta. Si mutara el del `load`, el resto de la pantalla vería los
    // agentes en otro orden sin motivo.
    const copia = [...inventario];
    agentesDe(inventario, departamentoPorId('operativo'));
    expect(inventario.map((a) => a.nombre)).toEqual(copia.map((a) => a.nombre));
  });
});

describe('la planta lista para dibujar', () => {
  const planta = plantaDe(departamentoPorId('operativo'), inventario);

  it('sienta a los agentes, el primero en el principal', () => {
    const principal = planta.puestos.find((p) => p.principal);
    const primero = agentesDe(inventario, departamentoPorId('operativo'))[0];
    expect(principal.agente).toBe(primero.nombre);
    expect(principal.nombre).toBe(primero.rotulo);
  });

  it('los puestos sin agente se dibujan vacíos y lo dicen', () => {
    // Inventarles un ocupante para que la escena no se vea sosa es la clase de
    // afirmación que esta pantalla no puede permitirse.
    const cuantos = agentesDe(inventario, departamentoPorId('operativo')).length;
    const libres = planta.puestos.filter((p) => !p.agente);
    expect(libres.length).toBe(planta.puestos.length - cuantos);
    expect(libres.every((p) => p.area === 'puesto libre')).toBe(true);
  });

  it('el cartel del muro lleva el rótulo del departamento', () => {
    expect(planta.cartel.rotulo).toBe('NOC y Redes');
    expect(typeof planta.cartel.gx).toBe('number');
  });

  it('sin inventario, cada sala se dibuja entera y vacía', () => {
    for (const d of DEPARTAMENTOS) {
      const sola = plantaDe(d, []);
      expect(sola.puestos, d.id).toHaveLength(d.planta.puestos.length);
      expect(sola.puestos.every((p) => p.agente === null), d.id).toBe(true);
    }
  });

  it('conserva mundo, pasillo y mobiliario del departamento', () => {
    const d = departamentoPorId('atencion_cliente');
    const p = plantaDe(d, inventario);
    expect(p.mundo).toEqual(d.planta.mundo);
    expect(p.pasillo).toEqual(d.planta.pasillo);
    expect(p.mobiliario).toEqual(d.planta.mobiliario);
  });

  it('un id desconocido no rompe: cae en el primero', () => {
    expect(departamentoPorId('no_existe')).toBe(DEPARTAMENTOS[0]);
  });
});

describe('la empresa entera, las seis salas a la vez', () => {
  const edificio = plantaDeLaEmpresa(inventario);

  it('están todas', () => {
    expect(edificio).toHaveLength(DEPARTAMENTOS.length);
  });

  it('NINGUNA sala se solapa con otra', () => {
    // Es la condición que sostiene la simplificación de la escena: ordena las
    // salas por la profundidad de su origen y dentro de cada una por la suya.
    // Si dos se tocaran habría que intercalar sus objetos uno a uno, y eso no
    // lo hace — el síntoma sería un muro de una sala apareciendo delante del
    // mobiliario de la vecina.
    for (const a of edificio) {
      for (const b of edificio) {
        if (a === b) continue;
        const solapaX = a.origen.gx < b.origen.gx + b.mundo.ancho &&
                        a.origen.gx + a.mundo.ancho > b.origen.gx;
        const solapaY = a.origen.gy < b.origen.gy + b.mundo.fondo &&
                        a.origen.gy + a.mundo.fondo > b.origen.gy;
        expect(solapaX && solapaY).toBe(false);
      }
    }
  });

  it('y el hueco entre vecinas cubre la ALTURA de un muro', () => {
    // Tres celdas no alcanzaban: un muro de cuatro unidades se proyecta más de
    // cien píxeles hacia arriba e invade la sala de atrás aunque en planta no
    // se toquen. El hueco se mide contra la altura, no contra el suelo.
    const alto = Math.max(...edificio.map((p) => p.mundo.alto));
    const porFila = {};
    for (const p of edificio) (porFila[p.origen.gy] = porFila[p.origen.gy] || []).push(p);
    for (const fila of Object.values(porFila)) {
      const orden = [...fila].sort((a, b) => a.origen.gx - b.origen.gx);
      for (let i = 1; i < orden.length; i++) {
        const hueco = orden[i].origen.gx - (orden[i - 1].origen.gx + orden[i - 1].mundo.ancho);
        expect(hueco).toBeGreaterThanOrEqual(alto);
      }
    }
  });

  it('los 21 puestos conservan identificadores únicos', () => {
    // La selección se guarda por id, y en la vista de empresa están los de las
    // seis salas a la vez: uno repetido marcaría dos puestos.
    const ids = edificio.flatMap((p) => p.puestos.map((q) => q.id));
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('se sientan SEIS de los nueve: tres son capacidades, no empleados', () => {
    // Es el arreglo P0.1. `soporte`, `facturacion` y `administracion` no son
    // empleados virtuales: son capacidades que se le asignan a una persona del
    // CRM. Dibujarles un escritorio era inventar tres empleados.
    //
    // Esta prueba FALLABA antes del arreglo, afirmando que los nueve se
    // sientan. Esa era exactamente la mentira.
    const sentados = new Set(
      edificio.flatMap((p) => p.puestos.map((q) => q.agente)).filter(Boolean)
    );
    expect(sentados.size).toBe(6);
    for (const capacidad of ['soporte', 'facturacion', 'administracion']) {
      expect(sentados.has(capacidad), `${capacidad} NO debería tener escritorio`).toBe(false);
    }
  });

  it('y ninguno de los nueve se pierde: o se sienta, o es capacidad declarada', () => {
    // No basta con no dibujarlos: si desaparecieran del todo, la oficina
    // estaría ocultando que existen.
    const sentados = new Set(
      edificio.flatMap((p) => p.puestos.map((q) => q.agente)).filter(Boolean)
    );
    const capacidades = new Set(
      edificio.flatMap((p) => p.capacidades.map((c) => c.nombre))
    );
    for (const a of inventario) {
      expect(sentados.has(a.nombre) || capacidades.has(a.nombre),
             `${a.nombre} no aparece ni sentado ni como capacidad`).toBe(true);
    }
  });

  it('una capacidad se resuelve contra el inventario, con su cargo', () => {
    const conCapacidades = edificio.filter((p) => p.capacidades.length > 0);
    expect(conCapacidades.length).toBeGreaterThan(0);
    for (const p of conCapacidades) {
      for (const c of p.capacidades) {
        expect(c.ausente, `${c.nombre} declarada y ausente del inventario`).toBe(false);
        expect(typeof c.cargo).toBe('string');
      }
    }
  });

  it('un agente declarado que el inventario NO trae deja el puesto vacío y dice por qué', () => {
    // Dibujarlo igual sería volver a inventar un empleado; callarlo sería un
    // hueco que nadie puede explicar.
    const solo = plantaDe(departamentoPorId('operativo'), []);
    const principal = solo.puestos.find((p) => p.principal);
    expect(principal.agente).toBeNull();
    expect(principal.motivo).toContain('supervisor_noc');
    expect(principal.area).toBe('agente no encontrado');
  });

  it('cada sala conserva su acento', () => {
    const acentos = edificio.map((p) => p.acento);
    expect(new Set(acentos).size).toBe(edificio.length);
  });
});
