import { describe, it, expect } from 'vitest';
import { saludDelCanal } from './canal.js';

/**
 * ESTAS PRUEBAS SON LA ÚNICA VERIFICACIÓN POSIBLE de dos de los cuatro
 * estados: en el entorno de QA `whatsapp_salidas` está vacía, así que en
 * pantalla sólo se puede ver "sin tráfico". Los otros tres no se pueden
 * producir sin sembrar envíos falsos, y se decidió no hacerlo.
 *
 * O sea que si esto se rompe, nadie lo va a ver mirando la Bandeja.
 */

const medida = (enviados, con_acuse, fallidos = 0, ventana_minutos = 60) =>
  ({ enviados, con_acuse, fallidos, ventana_minutos });

describe('«no sé» no es «está bien»', () => {
  it('sin medición no afirma nada', () => {
    expect(saludDelCanal(null).estado).toBe('no_medido');
    expect(saludDelCanal(undefined).estado).toBe('no_medido');
  });

  it('null en enviados es «no se pudo medir», no cero', () => {
    // El motor devuelve null cuando la consulta falló. Tratarlo como 0 diría
    // "sin tráfico" sobre un canal que quizá está escupiendo errores.
    const r = saludDelCanal(medida(null, null, null));
    expect(r.estado).toBe('no_medido');
    expect(r.alerta).toBe(false);
  });

  it('sin tráfico NO dice que el canal esté bien', () => {
    const r = saludDelCanal(medida(0, 0));
    expect(r.estado).toBe('sin_trafico');
    expect(r.alerta).toBe(false);
    expect(r.detalle).toMatch(/no hay con qué comprobar/i);
  });
});

describe('la falla que este indicador existe para ver', () => {
  it('varios envíos y CERO acuses: alerta', () => {
    // Es D17: los mensajes salen, los acuses no vuelven, nadie se entera.
    const r = saludDelCanal(medida(18, 0));
    expect(r.estado).toBe('sin_acuses');
    expect(r.alerta).toBe(true);
    expect(r.detalle).toMatch(/18 mensajes/);
  });

  it('pero con pocos envíos no grita: un acuse puede tardar', () => {
    expect(saludDelCanal(medida(4, 0)).estado).toBe('ok');
    expect(saludDelCanal(medida(4, 0)).alerta).toBe(false);
  });

  it('el umbral es cinco, y se cumple en el borde', () => {
    expect(saludDelCanal(medida(4, 0)).estado).toBe('ok');
    expect(saludDelCanal(medida(5, 0)).estado).toBe('sin_acuses');
  });

  it('con UN solo acuse ya no es la falla: el webhook llega', () => {
    // Que falten acuses puede ser demora; que no llegue NINGUNO es otra cosa.
    const r = saludDelCanal(medida(20, 1));
    expect(r.estado).toBe('ok');
    expect(r.alerta).toBe(false);
  });
});

describe('los fallos de envío acompañan, no deciden', () => {
  it('se nombran en el detalle', () => {
    // No cambian el estado a propósito: un envío fallido ya se ve en el hilo,
    // marcado y con su reintento. El indicador de la barra es para lo que NO
    // se ve en ningún otro lado.
    const r = saludDelCanal(medida(20, 20, 3));
    expect(r.estado).toBe('ok');
    expect(r.detalle).toMatch(/3 sin poder enviarse/);
  });

  it('sin fallos no se menciona el cero', () => {
    expect(saludDelCanal(medida(20, 20, 0)).detalle).not.toMatch(/sin poder enviarse/);
  });
});

describe('la ventana se dice, no se asume', () => {
  it('el detalle nombra los minutos que se miraron', () => {
    expect(saludDelCanal(medida(10, 10, 0, 15)).detalle).toMatch(/15 min/);
    expect(saludDelCanal(medida(0, 0, 0, 15)).detalle).toMatch(/15 min/);
  });
});
