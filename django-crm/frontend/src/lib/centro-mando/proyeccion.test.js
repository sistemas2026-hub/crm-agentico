import { describe, it, expect } from 'vitest';
import { proyectar, vigentes, estadoDeAgentes } from './proyeccion.js';

/**
 * Lo que se fija acá es, sobre todo, lo que el proyector NO hace: no inventa
 * agentes, no inventa destinos, no convierte una llamada terminada en trabajo
 * en curso y no deja nada encendido para siempre.
 *
 * Una pantalla que se mira para saber cómo va la operación solo vale si cada
 * cosa que se mueve se puede rastrear hasta un hecho registrado.
 */

/** Los que EXISTEN como instancia ejecutable y tienen personaje. */
const AGENTES = ['cliente_final', 'facturacion_cliente', 'soporte_tecnico_cliente',
                 'ventas', 'supervisor_noc', 'configuracion_guiada'];
const AREAS = ['facturacion_cliente', 'soporte_tecnico_cliente', 'ventas'];
const CTX = { agentes: AGENTES, areas: AREAS, ahora: 1_000_000 };

const ev = (extra = {}) => ({
  id: extra.id ?? crypto.randomUUID(),
  en: '2026-10-29T17:00:00.000Z',
  agente: 'soporte_tecnico_cliente',
  tipo: 'consulta',
  herramienta: 'consultar_olt',
  duracion_ms: 400,
  datos: {},
  ...extra
});

describe('A9 · ninguna instrucción operativa sin evento que la respalde', () => {
  it('toda instrucción lleva el uuid del evento en su procedencia', () => {
    const { instrucciones } = proyectar([ev(), ev({ tipo: 'accion' })], CTX);
    expect(instrucciones).toHaveLength(2);
    for (const i of instrucciones) {
      expect(i.procedencia).toBe(`evento:${i.id}`);
      expect(i.id).toBeTruthy();
    }
  });

  it('un evento SIN id no se proyecta', () => {
    // Sin identidad no se puede rastrear hasta el hecho: sería decoración
    // disfrazada de dato.
    const { instrucciones, descartados } = proyectar([ev({ id: null })], CTX);
    expect(instrucciones).toHaveLength(0);
    expect(descartados.sin_evento).toBe(1);
  });

  it('el reposo lleva procedencia "ambiente", nunca un uuid', () => {
    const estados = estadoDeAgentes([], AGENTES, CTX.ahora);
    expect(estados.every((e) => e.tipo === 'reposo')).toBe(true);
    expect(estados.every((e) => e.procedencia === 'ambiente')).toBe(true);
  });
});

describe('duplicados y eventos fuera de orden', () => {
  it('el mismo evento dos veces produce UNA instrucción', () => {
    // El flujo puede entregarlo repetido: es el precio de no perder ninguno
    // en la transición foto -> cursor. Animarlo dos veces contaría una
    // actividad que ocurrió una.
    const uno = ev({ id: 'a1b2' });
    const { instrucciones, descartados } = proyectar([uno, { ...uno }], CTX);
    expect(instrucciones).toHaveLength(1);
    expect(descartados.repetido).toBe(1);
  });

  it('el orden de llegada no cambia lo que se proyecta', () => {
    const a = ev({ id: 'x1', en: '2026-10-29T17:00:02.000Z' });
    const b = ev({ id: 'x2', en: '2026-10-29T17:00:01.000Z' });
    const ordenados = proyectar([b, a], CTX).instrucciones.map((i) => i.id);
    const alReves = proyectar([a, b], CTX).instrucciones.map((i) => i.id);
    expect(ordenados.sort()).toEqual(alReves.sort());
  });

  it('un evento incompleto no revienta ni inventa', () => {
    const { instrucciones } = proyectar([null, undefined, {}, ev()], CTX);
    expect(instrucciones).toHaveLength(1);
  });
});

describe('identidad del agente', () => {
  it('un rol que NO es instancia ejecutable no se dibuja', () => {
    // 'soporte' es una CAPACIDAD asignada a una persona, no un empleado
    // virtual. Pintarle escritorio sería inventar un empleado.
    const { instrucciones, descartados } = proyectar(
      [ev({ agente: 'soporte' }), ev({ agente: 'facturacion' })], CTX);
    expect(instrucciones).toHaveLength(0);
    expect(descartados.agente_desconocido).toBe(2);
  });

  it('un agente inventado tampoco', () => {
    const { instrucciones } = proyectar([ev({ agente: 'agente_fantasma' })], CTX);
    expect(instrucciones).toHaveLength(0);
  });

  it('sin agente no hay instrucción', () => {
    const { instrucciones } = proyectar([ev({ agente: null })], CTX);
    expect(instrucciones).toHaveLength(0);
  });
});

describe('derivación: expediente, no caminata', () => {
  it('un área válida produce un expediente hacia ese destino', () => {
    const { instrucciones } = proyectar(
      [ev({ datos: { area: 'facturacion_cliente' } })], CTX);
    expect(instrucciones[0].tipo).toBe('expediente');
    expect(instrucciones[0].destino).toBe('facturacion_cliente');
  });

  it('un área que la empresa NO tiene no se dibuja', () => {
    // El destino sale del evento real. Inventarlo sería mostrar una ruta que
    // no existe en esta empresa.
    const { instrucciones, descartados } = proyectar(
      [ev({ datos: { area: 'departamento_que_no_existe' } })], CTX);
    expect(instrucciones).toHaveLength(0);
    expect(descartados.tipo_desconocido).toBe(1);
  });

  it('el personaje NO se mueve: la instrucción es del expediente', () => {
    const { instrucciones } = proyectar(
      [ev({ datos: { area: 'ventas' } })], CTX);
    expect(instrucciones[0].tipo).toBe('expediente');
    expect(instrucciones[0].tipo).not.toBe('camina');
  });
});

describe('actividad pasada ≠ ejecución activa', () => {
  it('toda instrucción CADUCA: nada queda encendido para siempre', () => {
    const { instrucciones } = proyectar([ev()], CTX);
    expect(instrucciones[0].caduca_en).toBeGreaterThan(CTX.ahora);
    expect(instrucciones[0].caduca_en).toBeLessThanOrEqual(CTX.ahora + 2500);
  });

  it('una herramienta LENTA no deja al personaje ocupado todo ese rato', () => {
    // 40 segundos de duración no son 40 segundos de animación: la animación
    // cuenta QUE pasó, no cuánto duró. Y sobre todo, la llamada YA TERMINÓ.
    const { instrucciones } = proyectar([ev({ duracion_ms: 40_000 })], CTX);
    expect(instrucciones[0].duracion_ms).toBeLessThanOrEqual(2500);
  });

  it('pasada la caducidad, el agente vuelve a reposo SOLO', () => {
    const { instrucciones } = proyectar([ev()], CTX);
    const despues = CTX.ahora + 10_000;
    expect(vigentes(instrucciones, despues)).toHaveLength(0);
    const estados = estadoDeAgentes(instrucciones, AGENTES, despues);
    const suyo = estados.find((e) => e.agente === 'soporte_tecnico_cliente');
    expect(suyo.tipo).toBe('reposo');
    expect(suyo.procedencia).toBe('ambiente');
  });

  it('mientras está vigente, el agente muestra esa actividad', () => {
    const { instrucciones } = proyectar([ev()], CTX);
    const estados = estadoDeAgentes(instrucciones, AGENTES, CTX.ahora + 100);
    const suyo = estados.find((e) => e.agente === 'soporte_tecnico_cliente');
    expect(suyo.tipo).toBe('consulta');
    expect(suyo.procedencia).toMatch(/^evento:/);
  });
});

describe('tipos desconocidos', () => {
  it('un tipo que esta versión no conoce NO se dibuja', () => {
    // Pintar algo genérico ante lo desconocido es cómo una pantalla empieza a
    // afirmar cosas que nadie midió.
    const { instrucciones, descartados } = proyectar(
      [ev({ tipo: 'algo_que_no_existe_todavia' })], CTX);
    expect(instrucciones).toHaveLength(0);
    expect(descartados.tipo_desconocido).toBe(1);
  });

  it('y se CUENTA, para que la pantalla pueda decirlo', () => {
    const { descartados } = proyectar(
      [ev({ tipo: 'raro' }), ev({ agente: 'soporte' }), ev({ id: null })], CTX);
    expect(descartados.tipo_desconocido + descartados.agente_desconocido +
           descartados.sin_evento).toBe(3);
  });
});

describe('sin datos sensibles en ninguna etiqueta', () => {
  it('la etiqueta sale del catálogo, no de la conversación', () => {
    const { instrucciones } = proyectar([ev({
      herramienta: 'consultar_olt',
      // Esto llega enmascarado desde el motor y AUN ASÍ no debe salir.
      datos: { motivo: '...ubre', cedula: '...6789' }
    })], CTX);
    const texto = JSON.stringify(instrucciones);
    expect(texto).not.toContain('6789');
    expect(texto).not.toContain('ubre');
    expect(instrucciones[0].etiqueta).toBe('consultar_olt');
  });

  it('el expediente muestra el área, no el motivo', () => {
    const { instrucciones } = proyectar([ev({
      datos: { area: 'ventas', motivo: '...ubre' }
    })], CTX);
    expect(JSON.stringify(instrucciones)).not.toContain('ubre');
    expect(instrucciones[0].etiqueta).toBe('→ ventas');
  });
});

describe('el contrato es independiente del motor gráfico', () => {
  it('no menciona nada de PixiJS, sprites ni píxeles', () => {
    const { instrucciones } = proyectar(
      [ev(), ev({ datos: { area: 'ventas' } })], CTX);
    const claves = new Set(instrucciones.flatMap((i) => Object.keys(i)));
    expect([...claves].sort()).toEqual(
      ['agente', 'caduca_en', 'destino', 'duracion_ms', 'en', 'etiqueta',
       'id', 'procedencia', 'tipo'].filter((k) => claves.has(k)).sort());
    const texto = JSON.stringify(instrucciones).toLowerCase();
    for (const prohibido of ['sprite', 'pixi', 'canvas', 'x:', 'y:', 'px']) {
      expect(texto).not.toContain(prohibido);
    }
  });

  it('los departamentos vienen de la configuración, no del código', () => {
    // Otra empresa tendrá otras áreas: si estuvieran fijas acá, el motor
    // visual sería de una sola empresa.
    const otra = { agentes: ['ventas'], areas: ['cobranzas'], ahora: 1 };
    const { instrucciones } = proyectar(
      [ev({ agente: 'ventas', datos: { area: 'cobranzas' } })], otra);
    expect(instrucciones[0].destino).toBe('cobranzas');
  });
});
