import { describe, it, expect } from 'vitest';
import { resumenDeCuenta } from './cuenta.js';

/**
 * Lo que debe el cliente: qué se dice con lo que contestó el motor
 * (10/11/2026). Lo que se protege es que «no se pudo» y «al día» nunca se
 * confundan: el «saldo» de la ficha decía 0,00 a un cliente que debía.
 */

describe('lo que debe el cliente', () => {
  it('con deuda: cuántas, cuánto, cuántas vencidas y la más antigua', () => {
    const r = resumenDeCuenta({
      disponible: true, facturas_pendientes: 2, monto_pendiente: '95000.00',
      facturas_vencidas: 1, vencimiento_mas_antiguo: '2026-10-05',
      link_de_pago: 'https://pagos.ejemplo.test/x', otros_medios_de_pago: ['Efecty: convenio 123']
    });
    expect(r).toEqual({
      tipo: 'debe', pendientes: 2, monto: '95000.00', vencidas: 1, masAntigua: '2026-10-05',
      incluyeSaldo: false, parcial: false, link: 'https://pagos.ejemplo.test/x',
      otrosMedios: ['Efecty: convenio 123']
    });
  });

  it('sin vencidas el motor no manda el campo, y se lee como cero', () => {
    const r = resumenDeCuenta({ disponible: true, facturas_pendientes: 1, monto_pendiente: '50000.00' });
    expect(r.tipo === 'debe' && r.vencidas).toBe(0);
  });

  it('dice si el total incluye saldo anterior y si el proveedor tenía más páginas', () => {
    const r = resumenDeCuenta({
      disponible: true, facturas_pendientes: 1, monto_pendiente: '10.00',
      incluye_saldo_anterior: true, completo: false
    });
    expect(r.tipo === 'debe' && [r.incluyeSaldo, r.parcial]).toEqual([true, true]);
  });

  it('cero pendientes es «al día»', () => {
    expect(resumenDeCuenta({ disponible: true, facturas_pendientes: 0 })).toEqual({ tipo: 'al_dia' });
  });
});

describe('«no se pudo» nunca se lee como «al día»', () => {
  for (const [caso, cuenta] of /** @type {const} */ ([
    ['el proveedor no contestó', { disponible: false, motivo: 'sin_conexion' }],
    ['el plazo venció', { disponible: false, motivo: 'sin_respuesta' }],
    ['el cálculo se negó', { disponible: false, motivo: 'no_calculable', detalle: 'el proveedor devolvio facturas de otro cliente' }],
    ['un disponible sin número', { disponible: true }]
  ])) {
    it(caso, () => {
      const r = resumenDeCuenta(cuenta);
      expect(r.tipo).toBe('no_se_pudo');
    });
  }

  it('el porqué del cálculo viaja, para que quien atiende no adivine', () => {
    const r = resumenDeCuenta({ disponible: false, motivo: 'no_calculable', detalle: 'hay saldo anterior arrastrado entre varias facturas' });
    expect(r.tipo === 'no_se_pudo' && r.detalle).toMatch(/saldo anterior/);
  });
});

describe('cuándo no hay nada que decir', () => {
  it('mientras viaja: consultando', () => {
    expect(resumenDeCuenta(undefined)).toEqual({ tipo: 'consultando' });
  });
  it('una empresa sin el cálculo configurado: nada, ni una alarma diaria', () => {
    expect(resumenDeCuenta({ disponible: false, motivo: 'sin_herramienta' })).toEqual({ tipo: 'nada' });
    expect(resumenDeCuenta(null)).toEqual({ tipo: 'nada' });
  });
  it('sin cliente identificado: se dice que falta eso', () => {
    expect(resumenDeCuenta({ disponible: false, motivo: 'sin_identificar' })).toEqual({ tipo: 'sin_identificar' });
  });
});
