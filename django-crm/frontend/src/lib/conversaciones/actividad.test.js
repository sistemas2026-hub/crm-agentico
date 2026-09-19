/**
 * El relevo contado en palabras (fase 1.6).
 *
 * Lo que protege: que la línea de actividad no afirme nada que el evento no
 * diga. Las aserciones que importan son las negativas — no atribuirle a nadie
 * un movimiento cuya autoría no consta, y no llamar «falló» a lo que el
 * contrato marca como incierto.
 */
import { describe, it, expect } from 'vitest';
import { actorDe, loQuePaso, lineaDeActividad } from './actividad.js';

const ev = (extra) => ({
  tipo: 'tomada', actor_tipo: 'operador', actor_nombre: 'Ana Pérez',
  datos: {}, creado_en: '2026-09-19T14:05:00Z', ...extra
});

describe('quién actuó', () => {
  it('una persona con nombre se nombra', () => {
    expect(actorDe(ev())).toBe('Ana Pérez');
  });

  it('la IA y el sistema se distinguen', () => {
    expect(actorDe(ev({ actor_tipo: 'ia', actor_nombre: null }))).toBe('Dexter IA');
    expect(actorDe(ev({ actor_tipo: 'sistema', actor_nombre: null }))).toBe('El sistema');
  });

  it('un actor que esta pantalla no conoce no recibe identidad', () => {
    expect(actorDe(ev({ actor_tipo: 'otra_cosa' }))).toBe('Sin registro');
    expect(actorDe(null)).toBe('Sin registro');
  });

  it('un operador sin nombre no se le atribuye a la IA ni a nadie concreto', () => {
    const a = actorDe(ev({ actor_nombre: '   ' }));
    expect(a).toBe('Alguien del equipo');
    expect(a).not.toBe('Dexter IA');
  });
});

describe('qué pasó', () => {
  it('distingue una reasignación de una devolución', () => {
    const r = loQuePaso(ev({
      tipo: 'reasignada',
      datos: { anterior_nombre: 'Luis Vargas', nuevo_nombre: 'Ana Pérez', motivo: 'cambio de turno' }
    }));
    expect(r.texto).toBe('Reasignada a Ana Pérez');
    expect(r.detalle).toContain('antes la llevaba Luis Vargas');
    expect(r.detalle).toContain('cambio de turno');

    const d = loQuePaso(ev({ tipo: 'devuelta_a_ia', datos: { version: 4 } }));
    expect(d.texto).toBe('Volvió a manos de la IA');
    expect(d.tono).toBe('ia');
    expect(d.texto).not.toBe(r.texto);
  });

  it('una reasignación sin anterior no inventa de quién venía', () => {
    const r = loQuePaso(ev({ tipo: 'reasignada', datos: { nuevo_nombre: 'Ana Pérez' } }));
    expect(r.detalle).toBeNull();
    expect(r.texto).not.toMatch(/de nadie|sin asignar/i);
  });

  it('una devolución incierta NO se cuenta como que falló', () => {
    const inc = loQuePaso(ev({ tipo: 'devolucion_fallida', datos: { resultado: 'incierto' } }));
    expect(inc.texto).toMatch(/no se pudo confirmar/i);
    expect(inc.texto).not.toMatch(/el mensaje no salió/i);

    const rech = loQuePaso(ev({ tipo: 'devolucion_fallida', datos: { resultado: 'rechazado' } }));
    expect(rech.texto).toMatch(/el mensaje no salió/i);
    expect(rech.texto).not.toBe(inc.texto);
  });

  it('sin_id y aceptado_sin_registro tampoco son un fallo', () => {
    for (const resultado of ['sin_id', 'aceptado_sin_registro', undefined]) {
      const r = loQuePaso(ev({ tipo: 'devolucion_fallida', datos: { resultado } }));
      expect(r.texto).toMatch(/no se pudo confirmar/i);
    }
  });

  it('un tipo que esta pantalla no conoce se muestra, no se esconde', () => {
    // Ocurrió algo y quedó registrado. Tragárselo dejaría un hueco en un
    // registro de auditoría.
    const r = loQuePaso(ev({ tipo: 'algo_nuevo_del_motor' }));
    expect(r.texto).toBe('algo nuevo del motor');
    expect(r.tono).toBe('neutro');
  });

  it('todos los tipos declarados por la base tienen su frase', () => {
    // Los diecinueve del check de relevo_eventos_tipo_check.
    const tipos = [
      'escalada', 'intervencion', 'devolucion_solicitada', 'devuelta_a_ia',
      'devolucion_fallida', 'caso_externo_cerrado', 'tomada', 'soltada', 'reasignada',
      'pendiente_interno_abierto', 'pendiente_interno_cerrado', 'evaluacion_revisada',
      'accion_propuesta_duplicada', 'accion_aprobada', 'accion_rechazada',
      'accion_vencida', 'accion_cancelada', 'accion_desconocida', 'cerrada'
    ];
    for (const tipo of tipos) {
      const r = loQuePaso(ev({ tipo }));
      // Si cae en el caso por defecto, el texto es el tipo con espacios.
      expect(r.texto).not.toBe(tipo.replaceAll('_', ' '));
      expect(r.texto.length).toBeGreaterThan(3);
    }
  });
});

describe('la línea completa', () => {
  it('lleva quién, qué y cuándo', () => {
    const l = lineaDeActividad(ev({ tipo: 'soltada' }));
    expect(l.quien).toBe('Ana Pérez');
    expect(l.texto).toBe('Ana Pérez la soltó');
    expect(l.cuando).toBe('2026-09-19T14:05:00Z');
  });

  it('un evento vacío no rompe ni inventa', () => {
    expect(() => lineaDeActividad(null)).not.toThrow();
    const l = lineaDeActividad(null);
    expect(l.quien).toBe('Sin registro');
    expect(l.cuando).toBeNull();
  });
});
