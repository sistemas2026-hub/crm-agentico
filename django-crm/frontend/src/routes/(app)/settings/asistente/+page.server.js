import { fail } from '@sveltejs/kit';
import {
  guardarDescripcionEmpresa,
  guardarPersonaAsistente,
  guardarPlazoVisitaTecnica,
  leerConfiguracionAsistente
} from '$lib/server/v2/asistente-config.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals }) {
  const config = await leerConfiguracionAsistente();
  return {
    config,
    // El motor no tiene identidad propia: quien decide si esto se puede
    // editar es el CRM, con el mismo criterio que /api/agentes. Esto es la
    // afordancia (esconder el boton); la accion vuelve a comprobarlo, porque
    // ocultar un boton no es un control de acceso.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async update({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        update: { error: 'Solo un administrador puede cambiar la personalidad del asistente.' }
      });
    }

    const form = await request.formData();
    const valores = {
      nombre_asistente: form.get('nombre_asistente')?.toString().trim() ?? '',
      tono: form.get('tono')?.toString() ?? '',
      longitud_respuesta: form.get('longitud_respuesta')?.toString() ?? '',
      instrucciones_adicionales: form.get('instrucciones_adicionales')?.toString().trim() ?? ''
    };

    try {
      await guardarPersonaAsistente(valores);
    } catch (/** @type {any} */ err) {
      // El texto viene del validador del motor y nombra el campo y el motivo.
      // Se pasa tal cual en vez de reemplazarlo por un mensaje generico: es la
      // diferencia entre "no se pudo guardar" y "el tono tiene que ser formal,
      // cercano o tecnico".
      return fail(400, {
        update: { error: err?.message || 'No se pudo guardar la personalidad del asistente.' }
      });
    }

    // Sin redirect: `load` se vuelve a correr despues de la accion y los
    // valores nuevos aparecen donde el usuario ya esta mirando.
    return { updated: true };
  },

  async updateEmpresa({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        updateEmpresa: { error: 'Solo un administrador puede cambiar esta informacion.' }
      });
    }

    const form = await request.formData();
    const descripcion = form.get('descripcion')?.toString().trim() ?? '';

    try {
      await guardarDescripcionEmpresa(descripcion);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        updateEmpresa: { error: err?.message || 'No se pudo guardar.' }
      });
    }

    return { updatedEmpresa: true };
  },

  async updatePlazo({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        updatePlazo: { error: 'Solo un administrador puede cambiar este plazo.' }
      });
    }

    const form = await request.formData();
    const dias = Number(form.get('dias'));
    if (!Number.isInteger(dias) || dias < 1) {
      return fail(400, { updatePlazo: { error: 'El plazo tiene que ser un numero entero de dias, mayor a 0.' } });
    }

    try {
      await guardarPlazoVisitaTecnica(dias);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        updatePlazo: { error: err?.message || 'No se pudo guardar el plazo.' }
      });
    }

    return { updatedPlazo: true };
  }
};
