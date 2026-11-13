/**
 * Avisos de campo: dónde quiere esta empresa que le avisen.
 *
 * Mismo patrón que la pantalla de SmartOLT: el rol decide quién edita, el
 * secreto va en un solo sentido, y hay botón de probar en la misma página donde
 * se pega el dato. Pegar una URL y no saber si sirve es como se pudren estas
 * configuraciones.
 */
import { fail } from '@sveltejs/kit';

import {
  borrarCanal,
  cambiarCanal,
  crearCanal,
  guardarDominio,
  leerAvisos,
  probarCanal
} from '$lib/server/v2/avisos-campo.js';

/** Lo que dice el backend cuando no alcanza el rol. Se repite acá para no
 *  depender de que el mensaje del servidor llegue en todos los caminos. */
const SIN_PERMISO = 'Solo gestión puede configurar los avisos.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  return await leerAvisos(locals);
}

/** @param {any} err */
function mensajeDe(err) {
  return err?.body?.detail || err?.message || 'No se pudo completar la acción.';
}

/** @type {import('./$types').Actions} */
export const actions = {
  async agregar({ request, locals }) {
    const form = await request.formData();
    const tipo = (form.get('tipo') ?? '').toString().trim();
    const destino = (form.get('destino') ?? '').toString().trim();
    const nombre = (form.get('nombre') ?? '').toString().trim();

    if (!tipo) return fail(400, { error: 'Elegí por dónde querés que avisen.' });
    if (!destino) {
      return fail(400, {
        error:
          tipo === 'correo'
            ? 'Escribí la dirección de correo.'
            : 'Pegá la URL del webhook.'
      });
    }

    try {
      await crearCanal(locals, { tipo, destino, nombre });
    } catch (/** @type {any} */ err) {
      // 403 viene del backend y se traduce acá para que la pantalla no muestre
      // un código. 409 es «ese destino ya está», que NO es un error de dato.
      if (err?.status === 403) return fail(403, { error: SIN_PERMISO });
      return fail(400, { error: mensajeDe(err) });
    }
    return { agregado: true };
  },

  async apagar({ request, locals }) {
    const form = await request.formData();
    const id = (form.get('id') ?? '').toString();
    const activo = form.get('activo') === 'true';
    if (!id) return fail(400, { error: 'Falta el canal.' });

    try {
      await cambiarCanal(locals, id, { activo });
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) return fail(403, { error: SIN_PERMISO });
      return fail(400, { error: mensajeDe(err) });
    }
    return { cambiado: true };
  },

  async borrar({ request, locals }) {
    const form = await request.formData();
    const id = (form.get('id') ?? '').toString();
    if (!id) return fail(400, { error: 'Falta el canal.' });

    try {
      await borrarCanal(locals, id);
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) return fail(403, { error: SIN_PERMISO });
      return fail(400, { error: mensajeDe(err) });
    }
    return { borrado: true };
  },

  /**
   * Probar NO devuelve `fail` cuando el mensaje no llega.
   *
   * Que el webhook de la empresa esté caído no es un error de esta página: es el
   * resultado de la prueba, y es justamente lo que se quería averiguar. Con un
   * `fail` la pantalla diría «no se pudo» y mandaría a buscar el problema en el
   * lugar equivocado.
   */
  async probar({ request, locals }) {
    const form = await request.formData();
    const id = (form.get('id') ?? '').toString();
    if (!id) return fail(400, { error: 'Falta el canal.' });

    try {
      const r = await probarCanal(locals, id);
      return r?.llego
        ? { probado: 'Llegó. Fijate en el canal.' }
        : { probado_mal: r?.error || 'No se pudo entregar.' };
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) return fail(403, { error: SIN_PERMISO });
      return fail(400, { error: mensajeDe(err) });
    }
  },

  async dominio({ request, locals }) {
    const form = await request.formData();
    // Vaciarlo es legítimo: sin dominio el aviso sale igual, sin enlace.
    const url = (form.get('url_base_app') ?? '').toString().trim();
    // A quién llama el técnico desde la app cuando algo no cuadra. Vaciarlo
    // también es legítimo: sin número la app no dibuja el botón, en vez de
    // ofrecer una llamada que no va a ningún lado.
    const telefono = (form.get('telefono_soporte') ?? '').toString().trim();

    try {
      await guardarDominio(locals, url, telefono);
    } catch (/** @type {any} */ err) {
      if (err?.status === 403) return fail(403, { error: SIN_PERMISO });
      return fail(400, { error: mensajeDe(err) });
    }
    return { dominio: true };
  }
};
