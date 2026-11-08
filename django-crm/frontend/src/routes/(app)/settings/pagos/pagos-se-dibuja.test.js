/**
 * LA PANTALLA DE PAGOS SE DIBUJA, EN SUS ESTADOS
 * ==============================================
 *
 * El render de servidor no valida todo lo que valida el navegador (no ve una
 * clave repetida en un {#each}, por ejemplo), pero sí atrapa lo que más duele de
 * una pantalla nueva: que no compile, o que reviente con un dato que falta.
 * Esta prueba renderiza la PÁGINA de verdad y afirma el efecto en cada estado:
 *
 * - el asistente no contesta  -> lo dice, y NO ofrece un formulario que no
 *   podría guardar nada;
 * - contestó y no hay nada    -> "Sin link de pago" y "Sin puntos de pago", con
 *   los botones de cargarlos;
 * - hay link y medios         -> muestra el SITIO (no el link entero, que puede
 *   llevar parámetros) y cada medio con su instrucción;
 * - dos medios con el MISMO nombre -> se dibujan los dos (el caso que deja una
 *   pantalla en blanco en el navegador si la clave del {#each} es el nombre);
 * - lo guardado no se pudo leer -> se avisa, no se muestra como "sin medios";
 * - quien no es administrador no ve ningún botón de editar.
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from 'svelte/server';

// El harness no resuelve los módulos de SvelteKit ($app/*). El panel del formulario
// solo usa `enhance` para enviar sin recargar: acá no hace falta que haga nada.
vi.mock('$app/forms', () => ({ enhance: () => ({ destroy() {} }) }));
vi.mock('$app/navigation', () => ({ goto: () => {}, invalidate: () => {}, invalidateAll: () => {} }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://x/settings/pagos'), params: {} } }));
vi.mock('$app/stores', () => ({ page: { subscribe: () => () => {} } }));
import Pagina from './+page.svelte';

const dibujar = (data, form = null) => render(Pagina, { props: { data, form } }).body;

const VACIO = { link: '', medios: [], medios_ilegibles: false };
const EFECTY = { nombre: 'Efecty', instruccion: 'Convenio 12345. Di tu cédula en caja.' };

describe('la pantalla de Pagos', () => {
  it('sin conexión con el asistente: lo dice y no ofrece guardar', () => {
    const html = dibujar({ ajustes: null, can_edit: true });
    expect(html).toContain('Sin conexión con el asistente');
    expect(html).not.toContain('Cargar el link');
    expect(html).not.toContain('Cambiar el link');
    expect(html).not.toContain('Agregar un medio');
  });

  it('sin nada cargado: lo dice en cada bloque y ofrece cargarlo', () => {
    const html = dibujar({ ajustes: VACIO, can_edit: true });
    expect(html).toContain('Sin link de pago');
    expect(html).toContain('Cargar el link');
    expect(html).toContain('Sin puntos de pago');
    expect(html).toContain('Agregar un medio');
    expect(html).not.toContain('undefined');
  });

  it('con link: muestra el sitio, no el link entero, y ofrece cambiarlo', () => {
    const html = dibujar({
      ajustes: { ...VACIO, link: 'https://pagos.ejemplo.co/rapilink?ref=secreto123' },
      can_edit: true
    });
    expect(html).toContain('pagos.ejemplo.co');
    expect(html).not.toContain('secreto123');
    expect(html).toContain('Cambiar el link');
  });

  it('con medios: cada uno sale con su instrucción, y se ofrece editarlos', () => {
    const html = dibujar({
      ajustes: { ...VACIO, medios: [EFECTY, { nombre: 'Banco', instruccion: 'Cuenta de ahorros 000-111.' }] },
      can_edit: true
    });
    expect(html).toContain('Efecty');
    expect(html).toContain('Convenio 12345. Di tu cédula en caja.');
    expect(html).toContain('Banco');
    expect(html).toContain('Editar los medios');
    expect(html).not.toContain('Sin puntos de pago</p>');
  });

  it('dos medios con el mismo nombre se dibujan los dos (no una clave repetida)', () => {
    const html = dibujar({
      ajustes: {
        ...VACIO,
        medios: [EFECTY, { nombre: 'Efecty', instruccion: 'Otro convenio 99999.' }]
      },
      can_edit: true
    });
    expect(html).toContain('Convenio 12345');
    expect(html).toContain('Otro convenio 99999.');
  });

  it('lo guardado que no se pudo leer se AVISA, no se muestra como "sin medios"', () => {
    const html = dibujar({ ajustes: { ...VACIO, medios_ilegibles: true }, can_edit: true });
    expect(html).toContain('no se pudo leer');
    expect(html).not.toContain('Sin puntos de pago</p>');
  });

  it('el panel dice a quién se le da (con deuda o preguntando dónde pagar) y a quién no', () => {
    const html = dibujar({ ajustes: VACIO, can_edit: true });
    expect(html).toContain('ya verificado');
    expect(html).toContain('deba algo o no');
    expect(html).toContain('no se pudo verificar');
    expect(html).not.toContain('no debe nada');
  });

  it('quien no es administrador ve lo cargado pero ningún botón de editar', () => {
    const html = dibujar({
      ajustes: { ...VACIO, link: 'https://pagos.ejemplo.co', medios: [EFECTY] },
      can_edit: false
    });
    expect(html).toContain('pagos.ejemplo.co');
    expect(html).toContain('Efecty');
    expect(html).not.toContain('Cambiar el link');
    expect(html).not.toContain('Cargar el link');
    expect(html).not.toContain('Editar los medios');
    expect(html).not.toContain('Agregar un medio');
  });
});
