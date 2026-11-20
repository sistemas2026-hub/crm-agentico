import { fail } from '@sveltejs/kit';
import {
  leerOrganizacion,
  guardarOrganizacion,
  organizacionDelFormulario
} from '$lib/server/v2/organizacion-config.js';

/**
 * LA PANTALLA QUE ORGANIZA LA EMPRESA.
 *
 * Es lo que convierte la oficina virtual en un producto: hasta acá, dar de alta
 * un ISP con otra estructura exigía editar `tenant_config` a mano. Acá se
 * crean, se mueven, se renombran y se borran pisos, departamentos y espacios.
 *
 * LA VALIDACIÓN NO ESTÁ ACÁ y no es un olvido. Las reglas de una organización
 * coherente viven en el esquema del motor, y el editor valida el documento
 * completo antes de escribir. Lo único que esta capa comprueba es el PERMISO —
 * y lo comprueba de nuevo en la acción aunque el botón esté escondido: ocultar
 * un botón no es un control de acceso.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ fetch, locals }) {
  const organizacion = await leerOrganizacion(locals, fetch);
  return {
    organizacion,
    //  Mismo criterio que /settings/bandeja: quién puede reorganizar la
    //  empresa lo decide el CRM, no el motor.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async update({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        update: { error: 'Solo un administrador puede reorganizar la empresa.' }
      });
    }

    const form = await request.formData();
    const organizacion = organizacionDelFormulario(form);

    //  La única comprobación de forma que se hace de este lado, y es por el
    //  mensaje: el motor rechazaría un departamento sin plantilla con un texto
    //  escrito para quien lee el esquema. Acá se dice en qué fila.
    for (const d of organizacion.departamentos) {
      if (!d.plantilla) {
        return fail(400, {
          update: { error: `El departamento «${d.rotulo}» no tiene sala elegida.` },
          organizacion
        });
      }
    }

    try {
      const guardada = await guardarOrganizacion(locals, fetch, organizacion);
      return { update: { ok: true }, organizacion: guardada };
    } catch (/** @type {any} */ e) {
      //  El mensaje del motor VIAJA TAL CUAL: es el que dice qué regla se
      //  rompió —«el área X la reclaman A y B»—, y traducirlo a «no se pudo
      //  guardar» perdería lo único útil que trae.
      return fail(400, { update: { error: e?.message || 'No se pudo guardar.' },
                         organizacion });
    }
  }
};
