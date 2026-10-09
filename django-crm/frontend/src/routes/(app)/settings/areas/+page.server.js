import { fail } from '@sveltejs/kit';
import { leerAreas, crearArea, editarArea, borrarArea } from '$lib/server/v2/areas.js';

/**
 * Las áreas de trabajo del equipo.
 *
 * Hasta el 08/10/2026 un área solo se podía crear con un script contra la
 * base. Cuando Rapilink necesitó el área 'ventas' --para que entraran 123
 * tickets que estaban esperando-- la creó quien opera el servidor, no el
 * administrador del ISP. Esta pantalla cierra eso.
 *
 * El área manda más de lo que parece: un caso no tiene campo de área, la
 * hereda de su responsable. Así que crear un área, asignarle gente y mapearle
 * un departamento del proveedor es lo que decide en qué columna cae cada
 * ticket, y si llega a crearse siquiera.
 */

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals, fetch }) {
  const { areas, areaPorPersona } = await leerAreas(locals, fetch);

  //  Cuánta gente tiene cada una. Es el dato que decide si se puede borrar, y
  //  el que explica por qué un área vacía no recibe tickets -- sin
  //  responsable, el importador no crea el caso.
  const personas = /** @type {Record<string, number>} */ ({});
  for (const area of Object.values(areaPorPersona)) {
    personas[area] = (personas[area] ?? 0) + 1;
  }

  return {
    areas: areas.map((/** @type {any} */ a) => ({ ...a, personas: personas[a.nombre] ?? 0 })),
    //  false = el asistente no contestó. La pantalla no puede distinguirlo de
    //  "esta empresa no tiene áreas" por el largo de la lista, y ofrecer
    //  "Nueva área" cuando el motor está caído lleva a un error al guardar.
    disponible: Array.isArray(areas) && areas.length > 0
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async crear({ request, locals, fetch }) {
    const form = await request.formData();
    const etiqueta = form.get('etiqueta')?.toString().trim() ?? '';
    const color = form.get('color')?.toString() ?? '#64748b';
    const icono = form.get('icono')?.toString() ?? 'edificio';

    if (!etiqueta) {
      return fail(400, { crear: { etiqueta, error: 'Escribí un nombre para el área.' } });
    }
    try {
      const area = await crearArea(locals, fetch, { etiqueta, color, icono });
      //  Se devuelve el nombre interno para mostrarlo una vez: NO es el que
      //  se escribió, y entender eso la primera vez evita la pregunta de por
      //  qué renombrar después no lo cambia.
      return { crear: { ok: true, nombre: area?.nombre, etiqueta } };
    } catch (/** @type {any} */ err) {
      return fail(400, { crear: { etiqueta, error: err?.message ?? 'No se pudo crear el área.' } });
    }
  },

  async editar({ request, locals, fetch }) {
    const form = await request.formData();
    const nombre = form.get('nombre')?.toString() ?? '';
    const cambios = {
      etiqueta: form.get('etiqueta')?.toString().trim() ?? '',
      color: form.get('color')?.toString() ?? '',
      icono: form.get('icono')?.toString() ?? ''
    };
    if (!cambios.etiqueta) {
      return fail(400, { editar: { nombre, error: 'El área necesita un nombre visible.' } });
    }
    try {
      await editarArea(locals, fetch, nombre, cambios);
      return { editar: { ok: true, nombre } };
    } catch (/** @type {any} */ err) {
      return fail(400, { editar: { nombre, error: err?.message ?? 'No se pudo guardar.' } });
    }
  },

  async borrar({ request, locals, fetch }) {
    const form = await request.formData();
    const nombre = form.get('nombre')?.toString() ?? '';
    try {
      await borrarArea(locals, fetch, nombre);
      return { borrar: { ok: true, nombre } };
    } catch (/** @type {any} */ err) {
      //  El motor rechaza con 409 y explica cuánta gente hay adentro. Ese
      //  texto se muestra tal cual: es más útil que "no se pudo borrar", y es
      //  la única forma de que quien lo intenta sepa qué hacer antes.
      return fail(400, { borrar: { nombre, error: err?.message ?? 'No se pudo borrar.' } });
    }
  }
};
