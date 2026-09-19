/**
 * Quién escribió cada mensaje del hilo (D30 / fase 1.3B).
 *
 * Lo que protege: que la pantalla no le atribuya a nadie un mensaje cuya
 * autoría no consta. Las dos aserciones que importan son negativas —un
 * mensaje humano NO puede quedar como IA, y uno sin origen tampoco—, porque
 * ése era exactamente el defecto: `rol='assistant'` cubre a la IA, a las
 * personas y a las filas históricas por igual.
 */
import { describe, it, expect } from 'vitest';
import { autorDe } from './formato.js';

const msg = (extra) => ({ rol: 'assistant', origen: null, autor_nombre: null, ...extra });

describe('los cinco orígenes del contrato', () => {
  it('cliente', () => {
    const a = autorDe(msg({ rol: 'user', origen: 'cliente' }));
    expect(a.etiqueta).toBe('Cliente');
    expect(a.clase).toBe('a-cliente');
  });

  it('IA', () => {
    expect(autorDe(msg({ origen: 'ia' })).etiqueta).toBe('Dexter IA');
  });

  it('humano con nombre: se muestra el nombre, no un rótulo genérico', () => {
    const a = autorDe(msg({ origen: 'humano', autor_nombre: 'Ana Pérez' }));
    expect(a.etiqueta).toBe('Ana Pérez');
    expect(a.quien).toBe('Ana Pérez');
    expect(a.clase).toBe('a-humano');
  });

  it('humano sin nombre: se dice que fue una persona, sin inventar cuál', () => {
    const a = autorDe(msg({ origen: 'humano' }));
    expect(a.etiqueta).toBe('Atención humana');
    expect(a.quien).toBeNull();
    expect(a.clase).toBe('a-humano');
  });

  it('humano con nombre en blanco se trata como sin nombre', () => {
    expect(autorDe(msg({ origen: 'humano', autor_nombre: '   ' })).etiqueta).toBe(
      'Atención humana'
    );
  });

  it('sistema', () => {
    expect(autorDe(msg({ origen: 'sistema' })).etiqueta).toBe('Sistema');
  });

  it('nota interna, con su autor si consta', () => {
    const a = autorDe(msg({ rol: 'nota', origen: 'humano', autor_nombre: 'Ana Pérez' }));
    expect(a.etiqueta).toBe('Nota interna');
    expect(a.quien).toBe('Ana Pérez');
    expect(a.clase).toBe('a-nota');
  });
});

describe('lo que NO se puede afirmar', () => {
  it('assistant + humano NO puede quedar como IA', () => {
    const a = autorDe(msg({ origen: 'humano', autor_nombre: 'Ana Pérez' }));
    expect(a.clase).not.toBe('a-ia');
    expect(a.etiqueta).not.toBe('Dexter IA');
  });

  it('assistant + origen NULL no se le atribuye a nadie', () => {
    const a = autorDe(msg({ origen: null }));
    expect(a.etiqueta).toBe('Origen no registrado');
    expect(a.clase).toBe('a-sin-registro');
    // Ninguna de las cinco identidades del contrato.
    expect(['a-ia', 'a-humano', 'a-sistema', 'a-cliente', 'a-nota']).not.toContain(a.clase);
    expect(a.quien).toBeNull();
  });

  it('origen ausente (ni siquiera la clave) se trata igual que NULL', () => {
    expect(autorDe({ rol: 'assistant' }).clase).toBe('a-sin-registro');
  });

  it('dos mensajes con el MISMO rol quedan distinguidos por su origen', () => {
    const ia = autorDe(msg({ origen: 'ia' }));
    const persona = autorDe(msg({ origen: 'humano', autor_nombre: 'Ana Pérez' }));
    const historico = autorDe(msg({ origen: null }));
    expect(new Set([ia.clase, persona.clase, historico.clase]).size).toBe(3);
  });

  it('una combinación que el motor todavía no tiene cae en neutro, no en una identidad', () => {
    const a = autorDe(msg({ rol: 'assistant', origen: 'un_origen_futuro' }));
    expect(a.clase).toBe('a-sin-registro');
    expect(a.etiqueta).toBe('Origen no registrado');
  });

  // Los que faltaban, y que dejaban pasar el defecto: la primera versión
  // clasificaba con `origen === 'cliente' || rol === 'user'`, así que un
  // `user` sin origen salía afirmado como Cliente.
  it('user + NULL no es Cliente: sin origen no hay nada que afirmar', () => {
    const a = autorDe({ rol: 'user', origen: null });
    expect(a.etiqueta).toBe('Origen no registrado');
    expect(a.clase).not.toBe('a-cliente');
  });

  it('user + origen desconocido tampoco es Cliente', () => {
    expect(autorDe({ rol: 'user', origen: 'origen_futuro' }).clase).toBe('a-sin-registro');
  });

  it('combinaciones incoherentes caen en neutro', () => {
    // El motor no produce ninguna de las dos; tratarlas como válidas sería
    // inventar una lectura de datos inconsistentes.
    expect(autorDe({ rol: 'assistant', origen: 'cliente' }).clase).toBe('a-sin-registro');
    expect(autorDe({ rol: 'user', origen: 'ia' }).clase).toBe('a-sin-registro');
  });

  it('un rol que esta pantalla no conoce no recibe identidad', () => {
    expect(autorDe({ rol: 'humano', origen: 'humano' }).clase).toBe('a-sin-registro');
  });

  it('un mensaje nulo no rompe ni inventa autor', () => {
    expect(() => autorDe(null)).not.toThrow();
    expect(autorDe(null).clase).toBe('a-sin-registro');
  });
});
