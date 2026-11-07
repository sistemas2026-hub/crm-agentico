import { describe, it, expect } from 'vitest';
import { crearDemostracion } from './demo.js';
import { proyectar } from './proyeccion.js';

/**
 * EL GUION DE DEMOSTRACIÓN, Y LA RAZÓN DE QUE NO SEA ALEATORIO.
 *
 * Con azar, cada demostración es distinta y «no vi la animación de fallo» no se
 * puede distinguir de «la animación de fallo no funciona». Con guion, lo que se
 * ve es siempre lo mismo y una ausencia es un defecto.
 *
 * Y la afirmación que de verdad protege algo: los identificadores son uuid de
 * verdad, para que la separación entre real y simulado NO dependa de que el dato
 * de prueba «se vea falso».
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function correr(guion, segundos, paso = 0.1) {
  const salida = [];
  for (let t = 0; t < segundos; t += paso) salida.push(...guion.avanzar(paso));
  return salida;
}

describe('los identificadores', () => {
  it('son uuid que el proyector acepta', () => {
    // Si fueran `e1`, `x2` y compañía, el proyector los rechazaría y la
    // demostración no se vería — y peor: la separación real/simulado parecería
    // funcionar por la forma del identificador y no por el origen del lote.
    const g = crearDemostracion({ agente: 'supervisor_noc', areaDerivacion: 'soporte_tecnico' });
    const eventos = correr(g, 25);
    expect(eventos.length).toBeGreaterThan(4);
    for (const e of eventos) expect(e.id).toMatch(UUID);
  });

  it('no se repiten', () => {
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    const ids = correr(g, 60).map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('y aun siendo uuid válidos, salen como simulados al proyectarse', () => {
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    const eventos = correr(g, 10);
    const p = proyectar(eventos, { agentes: ['supervisor_noc'], simulado: true });
    expect(p.instrucciones.length).toBeGreaterThan(0);
    for (const i of p.instrucciones) expect(i.procedencia).toBe('simulado');
    expect(p.descartados.id_invalido).toBe(0);
  });
});

describe('el guion recorre las cinco animaciones', () => {
  it('produce consulta, acción, fallo, derivación y escalada', () => {
    const g = crearDemostracion({ agente: 'supervisor_noc', areaDerivacion: 'soporte_tecnico' });
    const p = proyectar(correr(g, 30), {
      agentes: ['supervisor_noc'],
      areas: ['soporte_tecnico'],
      simulado: true
    });
    const tipos = new Set(p.instrucciones.map((i) => i.tipo));
    expect([...tipos].sort()).toEqual(['accion', 'consulta', 'escalada', 'expediente', 'falla']);
  });

  it('tiene una pausa, para poder ver el reposo', () => {
    // Sin ella el personaje nunca para y no se puede comprobar que vuelve solo
    // a reposo al caducar la instrucción.
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    expect(g.pasos).toBeGreaterThan(5);
    // En una ventana de 7 s al final del ciclo no sale nada.
    correr(g, 20);
    const quietos = correr(g, 7, 0.05);
    expect(quietos.length).toBeLessThanOrEqual(2);
  });

  it('es el mismo guion en dos corridas', () => {
    const a = correr(crearDemostracion({ agente: 'x' }), 30).map((e) => e.tipo);
    const b = correr(crearDemostracion({ agente: 'x' }), 30).map((e) => e.tipo);
    expect(a).toEqual(b);
  });
});

describe('no se inventan destinos', () => {
  it('sin área configurada, la derivación se salta', () => {
    // Dibujar una derivación hacia un área que la empresa no tiene sería
    // mostrar una ruta que no existe.
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    const eventos = correr(g, 30);
    expect(eventos.filter((e) => e.datos?.area)).toEqual([]);
  });

  it('con área configurada, la derivación lleva ESA área', () => {
    const g = crearDemostracion({ agente: 'supervisor_noc', areaDerivacion: 'cartera' });
    const conArea = correr(g, 30).filter((e) => e.datos?.area);
    expect(conArea.length).toBeGreaterThan(0);
    for (const e of conArea) expect(e.datos.area).toBe('cartera');
  });
});

describe('el reloj', () => {
  it('un salto de tiempo no atasca el guion', () => {
    // Al volver de una pestaña oculta el navegador entrega varios segundos de
    // golpe. Con un `if` en vez de un `while`, el guion emitiría un paso por
    // fotograma durante un rato y la escena se volvería loca.
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    const deGolpe = g.avanzar(28);
    expect(deGolpe.length).toBeGreaterThan(3);
    const siguiente = g.avanzar(0.05);
    expect(siguiente.length).toBe(0);
  });

  it('reiniciar vuelve al principio', () => {
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    const primero = correr(g, 2)[0];
    g.reiniciar();
    const otra = correr(g, 2)[0];
    expect(otra.tipo).toBe(primero.tipo);
    expect(otra.herramienta).toBe(primero.herramienta);
  });

  it('cuenta cuántos emitió', () => {
    const g = crearDemostracion({ agente: 'supervisor_noc' });
    const eventos = correr(g, 20);
    expect(g.emitidos).toBe(eventos.length);
  });
});

describe('todos los eventos son del agente que se le pasó', () => {
  it('no hay un nombre de agente escrito en el guion', () => {
    // Si lo hubiera, la demostración animaría a un agente que esta empresa no
    // tiene, y el prototipo dejaría de servir para la siguiente.
    const g = crearDemostracion({ agente: 'un_nombre_cualquiera' });
    const eventos = correr(g, 30);
    expect(eventos.length).toBeGreaterThan(0);
    for (const e of eventos) expect(e.agente).toBe('un_nombre_cualquiera');
  });
});
