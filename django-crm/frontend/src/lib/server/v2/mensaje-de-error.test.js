import { describe, it, expect } from 'vitest';
import { mensajeDeError } from './mensaje-de-error.js';

/**
 * El motivo de un fallo, dicho como lo explicó el backend.
 *
 * Esto existe porque tres pantallas leían el error de tres lugares distintos y
 * **ninguna leía donde el dato está**: `apiRequest` cuelga `.body`, no `.data`,
 * y el backend de campo manda `{"error": "<CODIGO>", "detalle": "<frase>"}`.
 * Despacho mostraba `NO_SE_PUDO_CREAR` a la persona; las otras dos buscaban
 * `detail` y se perdían `detalle`.
 *
 * Cada caso de abajo es uno de esos errores REALES, copiado de
 * `campo/despacho_views.py` y de DRF.
 */

/** Como lo lanza `apiRequest`: un Error con `.status` y `.body`. */
const comoLoLanza = (status, body, message) =>
  Object.assign(new Error(message ?? ''), { status, body });

describe('mensajeDeError', () => {
  it('prefiere `detalle` sobre el código de `error`', () => {
    //  `campo/despacho_views.py:386` -> {"error": "YA_PROGRAMADA", "detalle": ...}
    const e = comoLoLanza(409, {
      error: 'YA_PROGRAMADA',
      detalle: 'La orden ya está programada para el 14/10.'
    }, 'YA_PROGRAMADA');

    expect(mensajeDeError(e)).toBe('La orden ya está programada para el 14/10.');
  });

  it('lee `detail` de DRF', () => {
    const e = comoLoLanza(400, { detail: 'No hay nada que publicar.' });
    expect(mensajeDeError(e)).toBe('No hay nada que publicar.');
  });

  it('cae al código solo si no hay frase: es lo único que hay', () => {
    const e = comoLoLanza(400, { error: 'VALIDACION_INVALIDA' });
    //  Feo, pero mejor que «no se pudo»: al menos se puede buscar en el log.
    expect(mensajeDeError(e)).toBe('VALIDACION_INVALIDA');
  });

  it('NO lee `.data`, que es donde nadie lo pone', () => {
    //  La mutación que esta prueba mata: volver a `e.data.detalle` haría pasar
    //  este caso con la frase, y es un objeto que `apiRequest` nunca produce.
    const e = /** @type {any} */ ({ data: { detalle: 'esto no existe' } });
    expect(mensajeDeError(e)).toBe('No se pudo completar la operación.');
  });

  it('saca el ruido del transporte, que no es el motivo', () => {
    const e = comoLoLanza(500, {}, 'HTTP 500: Internal Server Error');
    expect(mensajeDeError(e)).toBe('Internal Server Error');

    const f = comoLoLanza(400, {}, 'Error 400: el campo zona es obligatorio');
    expect(mensajeDeError(f)).toBe('el campo zona es obligatorio');
  });

  it('una frase en blanco no cuenta como frase', () => {
    const e = comoLoLanza(400, { detalle: '   ', detail: 'Falta la fecha.' });
    //  Un `detalle` vacío no puede tapar al `detail` que sí dice algo.
    expect(mensajeDeError(e)).toBe('Falta la fecha.');
  });

  it('`error` no-string no se muestra: es un diccionario de campos', () => {
    //  DRF manda {"error": {"zona": ["requerido"]}} en algunos serializers.
    //  Pegarlo como texto daría «[object Object]» en la pantalla.
    const e = comoLoLanza(400, { error: { zona: ['requerido'] } });
    expect(mensajeDeError(e)).toBe('No se pudo completar la operación.');
  });

  it('respeta la frase por defecto de cada pantalla', () => {
    expect(mensajeDeError({}, 'No se pudo despachar.')).toBe('No se pudo despachar.');
  });

  it('un error sin nada adentro no revienta', () => {
    expect(mensajeDeError(undefined)).toBe('No se pudo completar la operación.');
    expect(mensajeDeError(null)).toBe('No se pudo completar la operación.');
  });
});
