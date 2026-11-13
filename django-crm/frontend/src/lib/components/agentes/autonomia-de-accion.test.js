/**
 * Lo que un agente hace solo con una accion, dibujado de verdad (02/11/2026).
 *
 * El mismo reporte, dos agentes, dos respuestas: es la razon de que esto viva
 * en cada agente y no en una sola pantalla para toda la empresa. Y una persona
 * que no es ADMIN ve el estado pero no la palanca.
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import AutonomiaDeAccion from './AutonomiaDeAccion.svelte';

const REINICIO = {
  accion: 'reiniciar_ont', candidata: true, elegible: true, no_critica: true, faltan: [],
  puede_ser_no_critica: true,
  por_agente: {
    soporte_tecnico_cliente: { autonoma: true, estado: 'activa', promocion_id: 'p5',
                               rol: 'soporte_tecnico_cliente' },
    soporte: { autonoma: false, estado: 'retirada', promocion_id: null },
    otro: { autonoma: false, estado: 'degradada', promocion_id: null }
  }
};
const PAGO = { accion: 'registrar_pago', candidata: false, elegible: false,
               no_candidata: ['efecto_no_verificable', 'sin_previas_en_codigo'] };

/** @param {any} props */
const dibujar = (props) => render(AutonomiaDeAccion, { props }).body;

describe('la autonomia de una accion, en cada agente', () => {
  it('el agente que la tiene: "Lo hace solo", y el ADMIN la puede quitar para ESE agente', () => {
    const html = dibujar({ accion: REINICIO, agente: 'soporte_tecnico_cliente', esAdmin: true });
    expect(html).toContain('Lo hace solo');
    expect(html).toContain('action="?/retirar"');
    expect(html).toContain('value="soporte_tecnico_cliente"');
    expect(html).not.toContain('action="?/promover"');
  });

  it('otro agente con la misma accion: "Pide aprobación", y se la puede dar', () => {
    const html = dibujar({ accion: REINICIO, agente: 'soporte', esAdmin: true });
    expect(html).toContain('Pide aprobación');
    expect(html).toContain('action="?/promover"');
    expect(html).toContain('value="soporte"');
    expect(html).toContain('No crítica');
  });

  it('quien no es ADMIN ve el estado, sin palanca', () => {
    const html = dibujar({ accion: REINICIO, agente: 'soporte', esAdmin: false });
    expect(html).toContain('Pide aprobación');
    expect(html).not.toContain('<form');
  });

  it('la que se degrado sola lo dice', () => {
    const html = dibujar({ accion: REINICIO, agente: 'otro', esAdmin: true });
    expect(html).toContain('La perdió sola');
  });

  it('una critica sin efecto medible: siempre una persona, y por que', () => {
    const html = dibujar({ accion: PAGO, agente: 'facturacion', esAdmin: true });
    expect(html).toContain('Siempre la aprueba una persona');
    expect(html).toContain('su efecto no se puede comprobar en código');
    expect(html).not.toContain('<form');
  });

  it('una candidata sin lo que le falta: dice que falta, sin boton', () => {
    const html = dibujar({ accion: { ...REINICIO, elegible: false, no_critica: false,
                                     faltan: [{ condicion: 'cero_fallidas', tiene: 1, necesita: 0 }] },
                           agente: 'soporte', esAdmin: true });
    expect(html).not.toContain('action="?/promover"');
    expect(html).toMatch(/fall/i);
  });

  it('cuando lo hace solo por la autorizacion general, lo dice', () => {
    const general = { ...REINICIO, por_agente: { nuevo: { autonoma: true, estado: 'activa', promocion_id: 'g1' } } };
    expect(dibujar({ accion: general, agente: 'nuevo', esAdmin: true }))
      .toContain('para todos los agentes');
    expect(dibujar({ accion: REINICIO, agente: 'soporte_tecnico_cliente', esAdmin: true }))
      .not.toContain('para todos los agentes');
  });

  it('si es critica: un ADMIN la puede cambiar, solo en las que tienen garantias', () => {
    const noCritica = dibujar({ accion: REINICIO, agente: 'soporte', esAdmin: true });
    expect(noCritica).toContain('action="?/criticidad"');
    expect(noCritica).toContain('Marcarla crítica');
    const critica = dibujar({ accion: { ...REINICIO, no_critica: false }, agente: 'soporte', esAdmin: true });
    expect(critica).toContain('Marcarla no crítica');
    expect(critica).toContain('name="confirmo"');
    expect(dibujar({ accion: PAGO, agente: 'facturacion', esAdmin: true })).not.toContain('?/criticidad');
    expect(dibujar({ accion: REINICIO, agente: 'soporte', esAdmin: false })).not.toContain('?/criticidad');
  });

  it('"Marcarla no crítica" solo donde el motor lo aceptaria (auditoria B4, 04/11/2026)', () => {
    const sinGarantias = { ...REINICIO, no_critica: false, puede_ser_no_critica: false };
    const html = dibujar({ accion: sinGarantias, agente: 'soporte', esAdmin: true });
    expect(html).not.toContain('Marcarla no crítica');
    expect(html).not.toContain('?/criticidad');
    // la que YA es no critica se puede volver a marcar critica siempre
    expect(dibujar({ accion: { ...REINICIO, puede_ser_no_critica: false }, agente: 'soporte', esAdmin: true }))
      .toContain('Marcarla crítica');
  });

  it('el resultado de un cambio se muestra solo en el agente donde se hizo', () => {
    const resultado = { accion: 'reiniciar_ont', rol: 'soporte', ok: 'promovida' };
    expect(dibujar({ accion: REINICIO, agente: 'soporte', esAdmin: true, resultado }))
      .toContain('Listo: este agente la hace solo.');
    expect(dibujar({ accion: REINICIO, agente: 'soporte_tecnico_cliente', esAdmin: true, resultado }))
      .not.toContain('Listo');
  });
});
