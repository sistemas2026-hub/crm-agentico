/**
 * LA PANTALLA DE PAGOS SE DIBUJA, EN SUS TRES ESTADOS
 * ===================================================
 *
 * El render de servidor no valida todo lo que valida el navegador (no ve una
 * clave repetida en un {#each}, por ejemplo), pero sí atrapa lo que más duele de
 * una pantalla nueva: que no compile, o que reviente con un dato que falta.
 * Esta prueba renderiza la PÁGINA de verdad y afirma el efecto en cada estado:
 *
 * - el asistente no contesta  -> lo dice, y NO ofrece un formulario que no
 *   podría guardar nada;
 * - contestó y no hay link    -> "Sin link de pago", con el botón de cargarlo;
 * - hay link                  -> muestra el SITIO (no el link entero, que puede
 *   llevar parámetros), con el botón de cambiarlo;
 * - quien no es administrador no ve el botón.
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

describe('la pantalla de Pagos', () => {
  it('sin conexión con el asistente: lo dice y no ofrece guardar', () => {
    const html = dibujar({ ajustes: null, can_edit: true });
    expect(html).toContain('Sin conexión con el asistente');
    expect(html).not.toContain('Cargar el link');
    expect(html).not.toContain('Cambiar el link');
  });

  it('sin link cargado: "Sin link de pago" y el botón para cargarlo', () => {
    const html = dibujar({ ajustes: { link: '' }, can_edit: true });
    expect(html).toContain('Sin link de pago');
    expect(html).toContain('Cargar el link');
    expect(html).not.toContain('undefined');
  });

  it('con link: muestra el sitio, no el link entero, y ofrece cambiarlo', () => {
    const html = dibujar({
      ajustes: { link: 'https://pagos.ejemplo.co/rapilink?ref=secreto123' },
      can_edit: true
    });
    expect(html).toContain('pagos.ejemplo.co');
    expect(html).not.toContain('secreto123');
    expect(html).toContain('Cambiar el link');
  });

  it('quien no es administrador no ve el botón de editar', () => {
    const html = dibujar({ ajustes: { link: 'https://pagos.ejemplo.co' }, can_edit: false });
    expect(html).toContain('pagos.ejemplo.co');
    expect(html).not.toContain('Cambiar el link');
    expect(html).not.toContain('Cargar el link');
  });
});
