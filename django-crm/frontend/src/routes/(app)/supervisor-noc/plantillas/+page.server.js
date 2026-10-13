import { fail } from '@sveltejs/kit';
import {
  leerPlantillas,
  leerPlantilla,
  crearPlantilla,
  publicarPlantilla,
  activarPlantilla,
  mensajeDePlantilla
} from '$lib/server/v2/plantillas.js';

/**
 * Plantillas de trabajo — Supervisor NOC.
 *
 * Hasta el 13/10/2026 no existía esta pantalla: una plantilla se creaba en el
 * admin de Django escribiendo JSON, o con un comando semilla. Cada empresa
 * trabaja distinto, así que eso dejaba a cada ISP esperando a un desarrollador
 * para algo que es suyo.
 *
 * `?editar=<id>` abre una en el editor. Va en la URL y no en un estado de la
 * página para que recargar no pierda dónde estabas.
 *
 * QUIÉN PUEDE: el backend exige rol de gestión para escribir y lo dice con un
 * 403; acá no se repite la regla, se muestra su mensaje.
 */

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies }) {
  const lista = await leerPlantillas({ cookies });
  const editar = url.searchParams.get('editar');

  let edicion = null;
  let edicionError = null;
  if (editar) {
    try {
      edicion = await leerPlantilla({ cookies }, editar);
    } catch (e) {
      edicionError = mensajeDePlantilla(e, 'No se pudo abrir esa plantilla.');
    }
  }
  return { ...lista, edicion, edicionError };
}

/** @param {FormData} f */
function definicionDel(f) {
  try {
    return JSON.parse(String(f.get('definicion') ?? ''));
  } catch {
    return null;
  }
}

/** @type {import('./$types').Actions} */
export const actions = {
  /** Adoptar una del catálogo: queda publicada como v1 de la empresa. */
  adoptar: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await crearPlantilla({ cookies }, { base: String(f.get('base') ?? '') });
      return { hecho: `«${r.nombre}» ya está disponible en Despacho.`, abrir: r.id };
    } catch (e) {
      return fail(e?.status ?? 502, { error: mensajeDePlantilla(e, 'No se pudo adoptar.') });
    }
  },

  /**
   * Una desde cero. Arranca con la definición de «Trabajo general» para que no
   * nazca vacía —el backend rechaza una plantilla que no pide nada— y se edita
   * después.
   */
  crear: async ({ request, cookies }) => {
    const f = await request.formData();
    const definicion = definicionDel(f);
    if (!definicion) return fail(400, { error: 'La plantilla llegó vacía.' });
    try {
      const r = await crearPlantilla({ cookies }, {
        nombre: String(f.get('nombre') ?? '').trim(),
        labor: String(f.get('labor') ?? '').trim(),
        definicion
      });
      return { hecho: `«${r.nombre}» creada. Ajustala y publicala.`, abrir: r.id };
    } catch (e) {
      return fail(e?.status ?? 502, { error: mensajeDePlantilla(e, 'No se pudo crear.') });
    }
  },

  publicar: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('id') ?? '');
    const definicion = definicionDel(f);
    if (!id || !definicion) return fail(400, { error: 'Faltan datos para publicar.' });
    //  Nombre y labor viajan SOLO si el formulario los trae. Mandarlos vacíos
    //  no es «sin cambios»: el backend borraría la labor, y una plantilla sin
    //  labor deja de repartirse sin que nada lo diga.
    /** @type {{ definicion: any, nombre?: string, labor?: string }} */
    const cuerpo = { definicion };
    if (f.has('nombre')) cuerpo.nombre = String(f.get('nombre')).trim();
    if (f.has('labor')) cuerpo.labor = String(f.get('labor')).trim();
    try {
      const r = await publicarPlantilla({ cookies }, id, cuerpo);
      if (!r.cambio) {
        return { hecho: 'No había cambios en el formulario: sigue la misma versión.' };
      }
      //  Lo que NO cambia se dice: las órdenes ya creadas conservan la
      //  versión con la que nacieron.
      const vivas = r.ordenes_vivas
        ? ` Las ${r.ordenes_vivas} órdenes abiertas siguen con la versión anterior.`
        : '';
      return { hecho: `Publicada la versión ${r.version}. Las órdenes nuevas salen con ella.${vivas}` };
    } catch (e) {
      return fail(e?.status ?? 502, { error: mensajeDePlantilla(e, 'No se pudo publicar.') });
    }
  },

  activar: async ({ request, cookies }) => {
    const f = await request.formData();
    const activo = String(f.get('activo')) === 'true';
    try {
      const r = await activarPlantilla({ cookies }, String(f.get('id') ?? ''), activo);
      return {
        hecho: activo
          ? `«${r.nombre}» vuelve a estar en Despacho.`
          : `«${r.nombre}» ya no aparece en Despacho. Las órdenes que la usan siguen igual.`
      };
    } catch (e) {
      return fail(e?.status ?? 502, { error: mensajeDePlantilla(e, 'No se pudo cambiar.') });
    }
  }
};
