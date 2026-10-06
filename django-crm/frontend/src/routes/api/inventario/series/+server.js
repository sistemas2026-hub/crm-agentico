import { json } from '@sveltejs/kit';
import { leerSeriesDisponibles } from '$lib/server/v2/inventario.js';

/**
 * Qué series hay en una ubicación, para poder ELEGIRLAS en vez de escribirlas.
 *
 * POR QUÉ UN PROXY Y NO EL `load` DE LA PÁGINA
 * La bodega de origen y el material se eligen en la pantalla, después de que la
 * página cargó. Traerlas en el `load` obligaría a recargar entera cada vez que
 * alguien cambia de bodega en el desplegable — y en un acta de varias líneas
 * eso pasa seguido.
 *
 * El navegador no habla con el backend directamente: no tiene las credenciales
 * de servidor y el backend no está expuesto a su origen. Por eso esto vive acá,
 * del lado del servidor de SvelteKit, igual que el resto del módulo.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ locals, cookies, url }) {
  if (!locals.user) {
    return json({ error: 'No autenticado' }, { status: 401 });
  }

  const ubicacion = (url.searchParams.get('ubicacion') ?? '').trim();
  const material = (url.searchParams.get('material') ?? '').trim();
  if (!ubicacion || !material) {
    return json({ series: [] });
  }

  // Sin series es un resultado legítimo —una bodega puede no tener ninguna de
  // ese material— y la pantalla lo dibuja distinto que un fallo. Por eso el
  // error viaja declarado y no como una lista vacía.
  const r = await leerSeriesDisponibles({ cookies }, ubicacion, material);
  return json(r);
}
