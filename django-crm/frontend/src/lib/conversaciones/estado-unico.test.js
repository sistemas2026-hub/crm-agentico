/**
 * La línea de estado única (04/11/2026).
 *
 * Lo que protege: que una conversación cerrada diga UNA cosa, y que una que
 * lleva la IA no se lea como escalada. Las dos eran las contradicciones de la
 * pantalla anterior.
 */
import { describe, it, expect } from 'vitest';
import { estadoDeLaConversacion, cierreDe } from './estado-unico.js';

const evCierre = (extra = {}) => ({
  tipo: 'cerrada',
  actor_tipo: 'operador',
  actor_nombre: 'Admin',
  creado_en: '2026-10-31T18:43:00Z',
  datos: { por: 'operador' },
  ...extra
});

describe('cerrada manda sobre todo lo demás', () => {
  it('cerrada con las banderas de escalada todavía puestas dice cerrada, no «IA no responde»', () => {
    const e = estadoDeLaConversacion({
      estado: 'cerrada', iaEnPausa: true, escalada: true, atendida: true,
      cierre: cierreDe([evCierre()], {})
    });
    expect(e.clave).toBe('cerrada');
    expect(e.texto).toMatch(/^Cerrada · la resolvió Admin el \d\d\/\d\d a las \d\d:\d\d$/);
    expect(e.texto + e.detalle).not.toMatch(/IA no responde|Espera a una persona/);
    expect(e.tono).toBe('neutro');
  });

  it('cerrada por el cliente o por plazo no nombra a una persona', () => {
    const porCliente = cierreDe([evCierre({ actor_nombre: null, actor_tipo: 'sistema', datos: { por: 'cliente' } })], {});
    expect(estadoDeLaConversacion({ estado: 'cerrada', cierre: porCliente }).texto)
      .toMatch(/^Cerrada · el cliente confirmó el /);
    const porPlazo = cierreDe([evCierre({ actor_nombre: 'Admin', datos: { por: 'plazo' } })], {});
    expect(estadoDeLaConversacion({ estado: 'cerrada', cierre: porPlazo }).texto).not.toContain('Admin');
  });

  it('una legada sin eventos nombra a quien la atendió, sin inventar la fecha', () => {
    const cierre = cierreDe([], { atendida_por: 'Laura' });
    const e = estadoDeLaConversacion({ estado: 'cerrada', cierre });
    expect(e.texto).toBe('Cerrada · la resolvió Laura');
  });

  it('sin nada que conste, dice cerrada a secas', () => {
    expect(estadoDeLaConversacion({ estado: 'cerrada', cierre: cierreDe(null, {}) }).texto).toBe('Cerrada');
  });

  it('el último cierre manda si hubo más de uno en el expediente', () => {
    const c = cierreDe([evCierre({ actor_nombre: 'Viejo' }), { tipo: 'reabierta' }, evCierre({ actor_nombre: 'Nuevo' })], {});
    expect(c?.quien).toBe('Nuevo');
  });
});

describe('abierta', () => {
  it('la que lleva la IA sin escalar NO se lee como escalada', () => {
    const e = estadoDeLaConversacion({ estado: 'abierta', iaEnPausa: false, escalada: false });
    expect(e.clave).toBe('ia');
    expect(e.texto).not.toMatch(/Escalada/);
  });

  it('escalada sin dueño ni respuesta es la única alerta de quien espera', () => {
    const e = estadoDeLaConversacion({ estado: 'abierta', iaEnPausa: true, escalada: true });
    expect(e).toMatchObject({ clave: 'espera', tono: 'alerta', detalle: 'la IA no responde' });
  });

  it('con dueño deja de ser alerta', () => {
    expect(estadoDeLaConversacion({ estado: 'abierta', iaEnPausa: true, escalada: true, esMia: true }).tono).toBe('humano');
    expect(estadoDeLaConversacion({ estado: 'abierta', iaEnPausa: true, escalada: true, asignadaA: 'Laura' }).texto)
      .toBe('La atiende Laura');
  });

  it('respondida por el equipo gana sobre «asignada»', () => {
    const e = estadoDeLaConversacion({ estado: 'abierta', iaEnPausa: true, escalada: true, atendida: true, esMia: true });
    expect(e.clave).toBe('respondida');
  });

  it('escalada sin pausa dice que el asistente sigue respondiendo', () => {
    const e = estadoDeLaConversacion({ estado: 'abierta', iaEnPausa: false, escalada: true });
    expect(e.detalle).toBe('el asistente sigue respondiendo');
    // En riesgo, no urgente: el rojo queda para quien espera sin respuesta.
    expect(e.tono).toBe('aviso');
  });
});
