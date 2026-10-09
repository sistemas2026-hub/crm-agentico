/**
 * Quién atiende vs. quién figura en el caso (D28).
 *
 * La aserción que sostiene la decisión: la pantalla nunca llama «dueño» al
 * conjunto del CRM. Ese nombre promete una sola persona y una autoridad que el
 * campo no tiene, y quien lo lea así va a querer «corregirlo» borrando a los
 * demás — que es exactamente lo que este trabajo existe para evitar.
 */
import { describe, it, expect } from 'vitest';
import {
  ETIQUETAS, vistaDeAsignados, nombreDePerfil, explicacion
} from './asignados.js';

const perfil = (nombre, extra = {}) => ({
  id: `perfil-${nombre}`,
  user_details: { id: `user-${nombre}`, name: nombre, ...extra }
});

describe('las dos cosas no se llaman igual', () => {
  it('nunca se dice «dueño» del conjunto del CRM', () => {
    const textos = Object.values(ETIQUETAS).join(' ').toLowerCase();
    expect(textos).not.toMatch(/dueñ|owner|propietari/);
  });

  it('la etiqueta de Dexter habla de quien atiende; la del CRM, de asignados', () => {
    expect(ETIQUETAS.dexter).toMatch(/a cargo en dexter/i);
    expect(ETIQUETAS.crm).toMatch(/asignados en crm/i);
    expect(ETIQUETAS.dexter).not.toBe(ETIQUETAS.crm);
  });
});

describe('los colaboradores se muestran, no se señalan como error', () => {
  it('quien no puso Dexter aparece como colaborador', () => {
    const v = vistaDeAsignados(
      { falta_agregar: false, colaboradores: [perfil('Luis')], sin_perfil: false },
      'Ana Gómez'
    );
    expect(v.aCargoEnDexter).toBe('Ana Gómez');
    expect(v.colaboradores).toEqual(['Luis']);
    expect(explicacion(v)).toMatch(/no las quita/i);
    // Y en ningún caso se sugiere quitarlos.
    expect(explicacion(v)).not.toMatch(/quitar|eliminar|sobra|corregir/i);
  });

  it('un caso sin diferencias no muestra nada', () => {
    const v = vistaDeAsignados(
      { falta_agregar: false, colaboradores: [], sin_perfil: false },
      'Ana Gómez'
    );
    expect(v.hayAlgoQueMostrar).toBe(false);
    expect(explicacion(v)).toBe('');
  });
});

describe('la diferencia se dice sin afirmar que algo falló', () => {
  it('pendiente de sincronizar no es un error', () => {
    const v = vistaDeAsignados({ falta_agregar: true, colaboradores: [] }, 'Ana');
    expect(v.pendienteDeSincronizar).toBe(true);
    expect(explicacion(v)).toMatch(/sincroniz/i);
    expect(explicacion(v)).not.toMatch(/error|falló|fallo/i);
  });

  it('sin perfil en el CRM se explica, no se reporta como falla', () => {
    const v = vistaDeAsignados({ sin_perfil: true, colaboradores: [] }, 'Ana');
    expect(v.sinPerfilEnCrm).toBe(true);
    expect(explicacion(v)).toMatch(/no tiene perfil/i);
    expect(explicacion(v)).not.toMatch(/error|falló/i);
    // No se puede arreglar reintentando, así que no se promete que se arregle.
    expect(explicacion(v)).not.toMatch(/sincroniz/i);
  });
});

describe('cómo se nombra a una persona', () => {
  it('por su nombre, y si no hay, por su correo', () => {
    expect(nombreDePerfil(perfil('Luis'))).toBe('Luis');
    expect(nombreDePerfil({ user_details: { email: 'l@x.co' } })).toBe('l@x.co');
    expect(nombreDePerfil({})).toBe('—');
    expect(nombreDePerfil(null)).toBe('—');
  });

  it('el nombre es para mostrar, nunca para decidir', () => {
    // El cruce de identidad lo hace el backend por User.id
    // (nucleo/relevo/asignados_crm.py). Acá sólo se pinta: dos personas
    // homónimas se ven igual y eso está bien, porque nada se decide con esto.
    const v = vistaDeAsignados(
      { colaboradores: [perfil('Ana'), perfil('Ana')], falta_agregar: false },
      'Ana'
    );
    expect(v.colaboradores).toEqual(['Ana', 'Ana']);
  });
});

describe('entradas incompletas no rompen la pantalla', () => {
  it('sin diferencia, no hay nada que mostrar', () => {
    const v = vistaDeAsignados(null);
    expect(v.hayAlgoQueMostrar).toBe(false);
    expect(v.colaboradores).toEqual([]);
    expect(explicacion(v)).toBe('');
  });
});
