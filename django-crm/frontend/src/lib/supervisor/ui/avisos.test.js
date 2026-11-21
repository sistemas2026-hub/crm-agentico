import { describe, it, expect, beforeEach, vi } from 'vitest';
import { avisar, avisarDelFormulario, avisos, quitarAviso } from './avisos.svelte.js';

beforeEach(() => {
  avisos.lista = [];
  vi.useRealTimers();
});

describe('los avisos del Supervisor', () => {
  it('un aviso bueno se va solo; un error no', () => {
    vi.useFakeTimers();
    avisar('Publicada.');
    avisar('No se pudo guardar.', { tono: 'error' });
    expect(avisos.lista).toHaveLength(2);
    vi.advanceTimersByTime(7000);
    expect(avisos.lista.map((a) => a.texto)).toEqual(['No se pudo guardar.']);
  });

  it('no más de tres a la vez', () => {
    for (const t of ['a', 'b', 'c', 'd']) avisar(t, { tono: 'error' });
    expect(avisos.lista.map((a) => a.texto)).toEqual(['b', 'c', 'd']);
  });

  it('se puede cerrar a mano', () => {
    avisar('x', { tono: 'error' });
    quitarAviso(avisos.lista[0].id);
    expect(avisos.lista).toHaveLength(0);
  });

  it('el resultado de un formulario: el error gana sobre lo hecho', () => {
    avisarDelFormulario({ hecho: 'ok', error: 'mal' });
    expect(avisos.lista[0]).toMatchObject({ texto: 'mal', tono: 'error' });
    avisarDelFormulario(null);
    avisarDelFormulario({});
    expect(avisos.lista).toHaveLength(1);
  });
});
