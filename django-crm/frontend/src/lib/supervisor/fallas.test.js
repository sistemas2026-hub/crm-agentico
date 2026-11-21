import { describe, it, expect } from 'vitest';
import { avance, duracion, estadoDeLaCaida, motivosLegibles, resumenDeFallas, textoDeDetencion, textoDelError, TIPO_ALERTA } from './fallas.js';

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
    expect(textoDelError('AVISO_SIN_INDICATIVO')).toMatch(/indicativo del país/);
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

describe('el estado de cada caída (rediseño del 21/11/2026)', () => {
  it('viva sin aviso es activa y roja; con aviso en curso, avisando', () => {
    expect(estadoDeLaCaida({ estado: 'confirmada' })).toEqual({ grupo: 'activa', texto: 'Activa · confirmada', tono: 'critico' });
    expect(estadoDeLaCaida({ estado: 'confirmada', aviso: { estado: 'en_curso' } }).grupo).toBe('avisando');
  });

  it('en verificación sigue activa pero en ámbar; resuelta es verde', () => {
    expect(estadoDeLaCaida({ estado: 'en_verificacion' }).tono).toBe('alerta');
    expect(estadoDeLaCaida({ estado: 'resuelta', aviso: { estado: 'terminado' } })).toMatchObject({ grupo: 'resuelta', tono: 'ok', texto: 'Restablecida' });
  });

  it('el resumen cuenta equipos solo de las vivas', () => {
    const r = resumenDeFallas([
      { estado: 'confirmada', equipos: 9 },
      { estado: 'detectada', equipos: 24, aviso: { estado: 'en_curso', enviados: 14, clientes: 21 } },
      { estado: 'resuelta', equipos: 17, aviso: { estado: 'terminado' } }
    ]);
    expect(r).toEqual({ activas: 2, equipos: 33, avisando: 1, avisados: 14, aprobados: 21, resueltas: 1 });
    expect(resumenDeFallas(null).activas).toBe(0);
  });

  it('la duración se dice en minutos, horas o días', () => {
    const ahora = Date.parse('2026-11-21T10:40:00Z');
    expect(duracion('2026-11-21T10:28:00Z', ahora)).toBe('12 min');
    expect(duracion('2026-11-21T07:42:00Z', ahora)).toBe('2 h 58 min');
    expect(duracion('2026-11-20T07:40:00Z', ahora)).toBe('1 d 3 h');
    expect(duracion(null, ahora)).toBe('');
  });

  it('los tipos de alerta de SmartOLT tienen nombre', () => {
    expect(TIPO_ALERTA.power).toBe('Energía');
  });
});
