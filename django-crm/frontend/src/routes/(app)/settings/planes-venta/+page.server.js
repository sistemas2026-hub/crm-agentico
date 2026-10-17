import { fail } from '@sveltejs/kit';
import {
  guardarPlanesVenta,
  leerPlanesVenta,
  sincronizarLocalidades,
  sincronizarPrecios
} from '$lib/server/v2/planes-venta.js';

const SOLO_ADMIN = 'Solo un administrador puede cambiar esto.';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  const datos = await leerPlanesVenta(locals, fetch);
  return {
    catalogo: datos?.catalogo ?? [],
    errorCatalogo: datos?.error_catalogo ?? null,
    planesVenta: datos?.planes_venta ?? [],
    localidades: datos?.localidades ?? [],
    precios: datos?.precios_de_planes ?? [],
    preciosActualizadoEn: datos?.precios_actualizado_en ?? null,
    localidadesActualizadoEn: datos?.localidades_actualizado_en ?? null,
    herramientas: datos?.herramientas ?? [],
    marcasPrecio: datos?.marcas_precio ?? { listado: null, detalle: null },
    huboRespuesta: datos !== null,
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  async guardar({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN') return fail(403, { error: SOLO_ADMIN, action: 'guardar' });

    const form = await request.formData();
    const crudo = form.get('datos')?.toString() ?? '[]';
    /** @type {any[]} */
    let planes;
    try {
      planes = JSON.parse(crudo);
    } catch {
      return fail(400, {
        error: 'Los datos del formulario llegaron mal formados.',
        action: 'guardar'
      });
    }

    try {
      await guardarPlanesVenta(locals, fetch, planes);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudo guardar la lista de planes.',
        action: 'guardar'
      });
    }
    return { guardado: true };
  },

  async sincronizar({ locals }) {
    if (locals.profile?.role !== 'ADMIN')
      return fail(403, { error: SOLO_ADMIN, action: 'sincronizar' });

    try {
      await sincronizarLocalidades(locals, fetch);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudo sincronizar las localidades.',
        action: 'sincronizar'
      });
    }
    return { sincronizado: true };
  },

  /**
   * Trae el precio de cada plan.
   *
   * Es otra acción que `sincronizar` y no una bandera suya: recorre un
   * catálogo distinto, tarda distinto, y mezclarlas haría que actualizar los
   * barrios saliera a pedir 50 precios sin que nadie lo pidiera.
   */
  async precios({ request, locals }) {
    if (locals.profile?.role !== 'ADMIN')
      return fail(403, { error: SOLO_ADMIN, action: 'precios' });

    // De donde salen los precios es configuración por empresa: si la
    // pantalla mandó las dos herramientas, el motor las guarda y ya no hay
    // que volver a elegirlas. Un ISP nuevo con otro proveedor no necesita
    // una sesión de código para esto.
    const datos = await request.formData();
    const listado = String(datos.get('listado') ?? '').trim();
    const detalle = String(datos.get('detalle') ?? '').trim();

    try {
      const r = await sincronizarPrecios(locals, fetch, { listado, detalle });
      const n = (r?.precios ?? []).length;
      return {
        preciosHecho:
          `${n} ${n === 1 ? 'plan' : 'planes'} con su precio.` +
          // Un tope silencioso haría creer que se recorrió todo el catálogo.
          (r?.truncado ? ' El catálogo se cortó por su tope: hay más planes.' : '')
      };
    } catch (/** @type {any} */ err) {
      return fail(400, {
        error: err?.message || 'No se pudieron sincronizar los precios.',
        action: 'precios',
        // La pantalla muestra los dos selectores cuando esto viene: el error
        // dice qué falta, no solo que falló.
        faltaElegir: err?.faltaElegir === true,
        herramientas: err?.herramientas ?? []
      });
    }
  }
};
