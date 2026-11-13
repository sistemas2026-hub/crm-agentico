import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Los errores del backend llegan en español (12/11/2026).
 *
 * El backend corre en inglés y `readableError` pasaba «This field is
 * required.» tal cual. Se prueba la función y, sobre todo, la CADENA: una
 * respuesta 400 de Django → `apiRequest` REAL (que la aplana a «campo:
 * mensaje») → la acción de una pantalla → lo que recibe la página. Solo se
 * sustituyen `fetch` y las variables de entorno.
 */
vi.mock('$env/dynamic/private', () => ({ env: { PRIVATE_DJANGO_API_URL: 'http://backend' } }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const { readableError, enEspanol } = await import('./form-errors.js');
const { ESCALATION_PRIORITIES } = await import('$lib/v2/enums.js');
const { actions } = await import('../../../routes/(app)/settings/escalation/+page.server.js');

describe('enEspanol', () => {
  it('traduce los mensajes por defecto de DRF que de verdad salen', () => {
    expect(enEspanol('This field is required.')).toBe('Este campo es obligatorio.');
    expect(enEspanol('This field may not be blank.')).toBe('Este campo no puede quedar vacío.');
    expect(enEspanol('Enter a valid email address.')).toBe('Escribí un correo válido.');
    expect(enEspanol('Ensure this field has no more than 255 characters.')).toBe('Máximo 255 caracteres.');
    expect(enEspanol('Ensure this value is greater than or equal to 0.')).toBe('Tiene que ser al menos 0.');
    expect(enEspanol('"URGENTE" is not a valid choice.')).toBe('«URGENTE» no es una opción válida.');
    expect(enEspanol('Invalid pk "9" - object does not exist.')).toBe('Lo que elegiste ya no existe. Recargá la página.');
    expect(enEspanol("You don't have permission to perform this action.")).toBe('No tenés permiso para hacer esto.');
    expect(enEspanol('No Lead matches the given query.')).toBe('No se encontró.');
  });

  it('respeta el «campo: mensaje; campo: mensaje» que arma apiRequest', () => {
    expect(enEspanol('email: Enter a valid email address.; name: This field is required.'))
      .toBe('email: Escribí un correo válido.; name: Este campo es obligatorio.');
    expect(enEspanol('name: This field is required., This field may not be blank.'))
      .toBe('name: Este campo es obligatorio., Este campo no puede quedar vacío.');
  });

  it('un mensaje con comas propias se traduce entero, no a pedazos', () => {
    expect(enEspanol('Date has wrong format. Use one of these formats instead: YYYY-MM-DD, hh:mm.'))
      .toBe('La fecha no tiene un formato válido.');
  });

  it('lo desconocido y lo que ya está en español pasan tal cual', () => {
    expect(enEspanol('Team already exists with this name')).toBe('Ya existe uno con ese nombre.');
    expect(enEspanol('Something only this view says')).toBe('Something only this view says');
    expect(enEspanol('No se pudo guardar la política.')).toBe('No se pudo guardar la política.');
  });
});

describe('readableError', () => {
  it('también traduce dentro del JSON anidado que ya sabía bajar', () => {
    const err = new Error('HTTP 400: {"errors": {"user_errors": {"email": ["Email already exists"]}}}');
    expect(readableError(err, 'x')).toBe('email: Ya hay una persona con ese correo.');
  });

  it('sin motivo, el texto de respaldo de la pantalla', () => {
    expect(readableError(new Error(''), 'No se pudo.')).toBe('No se pudo.');
  });
});

describe('la cadena: Django → apiRequest → acción → página', () => {
  beforeEach(() => {
    globalThis.fetch = /** @type {any} */ (vi.fn(async () => ({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({ first_response_target_id: ['This field is required.'],
                           priority: ['"X" is not a valid choice.'] })
    })));
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('lo que recibe la página de Escalamiento está en español', async () => {
    const fd = new FormData();
    fd.append('priority', ESCALATION_PRIORITIES[0]);
    fd.append('first_response_action', 'notify');
    const r = /** @type {any} */ (await actions.create(/** @type {any} */ ({
      request: { formData: async () => fd },
      cookies: { get: () => 'jwt' }
    })));
    expect(r.status).toBe(400);
    expect(r.data.create.error).toBe(
      'first_response_target_id: Este campo es obligatorio.; priority: «X» no es una opción válida.'
    );
    expect(r.data.create.error).not.toMatch(/required|valid choice/);
  });
});
