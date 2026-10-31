import { describe, it, expect } from 'vitest';
import { avance, motivosLegibles, textoDeDetencion, textoDelError } from './fallas.js';

/**
 * «Fallas de red»: lo que lee quien aprueba el aviso (30/10/2026).
 * Un código desconocido se muestra tal cual: esconderlo es peor.
 */

describe('textoDelError', () => {
  it('traduce los códigos del backend', () => {
    expect(textoDelError('YA_APROBADO')).toBe('Ya se aprobó el aviso de esta caída.');
    expect(textoDelError('corte_de_energia')).toMatch(/corte de energía/);
  });

  it('un aviso que no está listo dice qué falta y que se encienda antes', () => {
    expect(textoDelError('AVISO_APAGADO')).toMatch(/apagado en Mensajes automáticos.*Encendelo/);
    expect(textoDelError('AVISO_PLANTILLA_NO_APROBADA')).toMatch(/no está aprobada por Meta/);
  });

  it('un código que no conoce se muestra tal cual', () => {
    expect(textoDelError('ALGO_NUEVO')).toBe('ALGO_NUEVO');
    expect(textoDelError('')).toBe('No se pudo completar la operación.');
  });
});

describe('motivosLegibles', () => {
  it('de mayor a menor, sin los que están en cero', () => {
    expect(motivosLegibles({ sin_movil: 2, de_baja: 5, rechazado: 0 })).toEqual([
      '5 pidieron no recibir mensajes',
      '2 sin celular en el ISP'
    ]);
  });

  it('un motivo nuevo se muestra con su código', () => {
    expect(motivosLegibles({ otro: 1 })).toEqual(['1 otro']);
  });
});

describe('textoDeDetencion', () => {
  it('dice por qué se detuvo un envío aprobado', () => {
    expect(textoDeDetencion('SITUACION_RESUELTA')).toMatch(/se resolvió/);
    expect(textoDeDetencion('VOLVIO_A_CAER')).toMatch(/no se le dijo a nadie que volvió/);
    expect(textoDeDetencion('AVISO_APAGADO')).toMatch(/apagado.*no recibieron/);
    expect(textoDeDetencion('')).toBe('');
    expect(textoDeDetencion('OTRO')).toBe('OTRO');
  });
});

describe('avance', () => {
  it('lo resuelto sobre el total', () => {
    expect(avance({ clientes: 40, pendientes: 10 })).toBe(75);
    expect(avance({ clientes: 0, pendientes: 0 })).toBe(0);
    expect(avance(null)).toBe(0);
  });
});
