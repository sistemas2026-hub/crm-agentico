/**
 * Lo que debe el cliente, dibujado en la pestaña Cliente (10/11/2026).
 *
 * Reemplaza al «saldo» de la ficha, que NO es lo que se debe: el 07/11 dijo
 * 0,00 a un cliente con una factura pendiente. Se afirma sobre lo que SALE:
 * la cifra del motor, nunca el saldo de la ficha, y «no se pudo» jamás
 * dibujado como «al día».
 */
import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import CustomerPanel from './CustomerPanel.svelte';

const texto = (/** @type {any} */ props) =>
  render(CustomerPanel, { props }).body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');

const conversacion = { id: 'c1', estado: 'abierta', usuario_externo: '573001112233', id_cliente: '77' };
// La ficha del 07/11: saldo 0,00 con una factura pendiente.
const ficha = { plan_internet: 'PLAN 300', saldo: '0.00', estado_facturas: 'Pendiente', fecha_corte: '2026-11-20' };

describe('lo que debe', () => {
  it('con deuda: el monto del motor, las pendientes, las vencidas y el link', () => {
    const t = texto({
      conversacion, ficha,
      cuenta: { disponible: true, facturas_pendientes: 2, monto_pendiente: '95000.00', facturas_vencidas: 1,
                vencimiento_mas_antiguo: '2026-10-05', link_de_pago: 'https://pagos.ejemplo.test/x' }
    });
    expect(t).toMatch(/Debe 95\.000/);
    expect(t).toMatch(/2 facturas pendientes\s*·\s*1 vencida/);
    expect(t).toMatch(/Copiar link de pago/);
  });

  it('el «saldo» de la ficha ya no se muestra: no es lo que se debe', () => {
    const t = texto({ conversacion, ficha, cuenta: { disponible: true, facturas_pendientes: 1, monto_pendiente: '50000.00' } });
    expect(t).not.toMatch(/Saldo/);
    // Lo que se dice es la cifra del motor (50.000), no el 0,00 de la ficha.
    expect(t).toMatch(/Debe 50\.000/);
    expect(t).not.toMatch(/(^|\D)0[,.]00/);
    // Lo demás de la ficha sigue: cobranza y corte.
    expect(t).toMatch(/Cobranza Pendiente/);
    expect(t).toMatch(/Fecha de corte/);
  });

  it('al día es al día, sin link', () => {
    const t = texto({ conversacion, ficha, cuenta: { disponible: true, facturas_pendientes: 0 } });
    expect(t).toMatch(/Al día: sin facturas pendientes/);
    expect(t).not.toMatch(/Copiar link/);
  });

  it('«no se pudo» dice por qué, y que eso no es estar al día', () => {
    const t = texto({ conversacion, ficha, cuenta: { disponible: false, motivo: 'no_calculable', detalle: 'el proveedor devolvio facturas de otro cliente' } });
    expect(t).toMatch(/No se pudo calcular lo que debe: el proveedor devolvio facturas de otro cliente/);
    expect(t).toMatch(/no quiere decir que esté al día/);
    expect(t).not.toMatch(/Al día:/);
  });

  it('mientras viaja: «Calculando», sin ninguna cifra', () => {
    const t = texto({ conversacion, ficha, cuenta: null, consultandoCuenta: true });
    expect(t).toMatch(/Calculando lo que debe/);
    expect(t).not.toMatch(/Debe \d/);
  });

  it('una empresa sin el cálculo configurado: la sección queda con lo de la ficha, sin alarma', () => {
    const t = texto({ conversacion, ficha, cuenta: { disponible: false, motivo: 'sin_herramienta' } });
    expect(t).not.toMatch(/No se pudo calcular/);
    expect(t).toMatch(/Cobranza Pendiente/);
  });
});
