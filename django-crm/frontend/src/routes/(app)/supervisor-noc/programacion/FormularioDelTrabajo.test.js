import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import FormularioDelTrabajo from './FormularioDelTrabajo.svelte';

/**
 * Lo que llenó el técnico, dibujado (18/10/2026).
 *
 * La forma de `form` es la que devuelve `campo/services/formulario_del_trabajo.py`
 * dentro de `GET /campo/trabajos/{id}/seguimiento/`, y la prueba del backend
 * (`test_formulario_del_trabajo.py`) la recorre por la vista. El proxy de la web
 * pasa esa respuesta entera. Acá se mide el último salto: que la pantalla dibuje
 * cada caso, y no solo que el dato llegue.
 */
// Sin los comentarios de hidratación de Svelte (`<!--[-1-->`), que no son
// parte de lo que se lee.
const pinta = (form) =>
  render(FormularioDelTrabajo, { props: { form } }).body.replace(/<!--[\s\S]*?-->/g, '');

const FORM = {
  campos: [
    { id: 'potencia_rx', titulo: 'Potencia Rx', valor: -19.5, obligatorio: true, sin_responder: false },
    { id: 'que_encontro', titulo: 'Qué encontró', valor: 'Otro: Roseta quemada', obligatorio: false, sin_responder: false },
    { id: 'cliente_conforme', titulo: 'Cliente conforme', valor: false, obligatorio: false, sin_responder: false },
    { id: 'serial', titulo: 'Serial de la ONT', valor: null, obligatorio: true, sin_responder: true },
    { id: 'campo_de_antes', titulo: 'campo_de_antes', valor: 'valor viejo', obligatorio: false,
      sin_responder: false, fuera_de_la_plantilla: true }
  ],
  fotos: [
    { requisito_id: 'foto_ont', titulo: 'Foto de la ONT', obligatorio: true, sin_foto: false,
      fotos: [
        { id: '11111111-1111-1111-1111-111111111111', disponible: true },
        { id: '22222222-2222-2222-2222-222222222222', disponible: false }
      ] },
    { requisito_id: 'foto_roseta', titulo: 'Foto de la roseta', obligatorio: true, sin_foto: true, fotos: [] }
  ]
};

describe('lo que llenó el técnico', () => {
  it('cada campo con su título y su valor, el «Otro» con su texto', () => {
    const b = pinta(FORM);
    expect(b).toContain('Potencia Rx:');
    expect(b).toContain('-19.5');
    expect(b).toContain('Otro: Roseta quemada');
  });

  it('un falso se lee «No», no como vacío', () => {
    const b = pinta(FORM);
    expect(b).toMatch(/Cliente conforme:<\/span>\s*<span[^>]*>\s*No/);
  });

  it('lo obligatorio sin responder se marca', () => {
    expect(pinta(FORM)).toContain('Sin responder · obligatorio');
  });

  it('lo escrito con una plantilla anterior se ve y se dice', () => {
    const b = pinta(FORM);
    expect(b).toContain('valor viejo');
    expect(b).toContain('de una plantilla anterior');
  });

  it('las fotos del checklist se ven, y la que no subió se dice', () => {
    const b = pinta(FORM);
    expect(b).toContain('/api/supervisor-noc/evidencias/11111111-1111-1111-1111-111111111111/archivo');
    expect(b).not.toContain('22222222-2222-2222-2222-222222222222');
    expect(b).toContain('Una foto todavía se está subiendo.');
  });

  it('una foto pedida que falta dice «Sin foto»', () => {
    const b = pinta(FORM);
    expect(b).toContain('Foto de la roseta');
    expect(b).toContain('Sin foto');
  });

  it('sin formulario ni fotos lo dice, en vez de un bloque vacío', () => {
    expect(pinta({ campos: [], fotos: [] })).toContain('no pide formulario ni fotos');
  });
});
