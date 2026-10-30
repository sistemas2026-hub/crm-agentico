import { json } from '@sveltejs/kit';

import { leerDiaPublicado } from '$lib/server/v2/dia-publicado.js';

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/**
 * Lo publicado de un día, para que Programación se actualice SOLA (30/10/2026).
 * El usuario: «estas tarjetas tienen que estar vivas: si manda un reporte
 * desde la app, que no se tenga que recargar la página ni presionar un botón;
 * solo y sin que se vea».
 *
 * La pantalla lo pide cada pocos segundos mientras está a la vista y cambia
 * los datos en su lugar. Aparte del load a propósito: aquel trae además el
 * material del día y su configuración, que no hace falta recalcular en cada
 * vuelta. Mismo permiso que la pantalla: solo quien gestiona.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ url, cookies, locals }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
  if (!ROLES_GESTION.has(rol)) {
    return json({ error: 'Esto es para quien gestiona.' }, { status: 403 });
  }
  const dia = (url.searchParams.get('dia') ?? '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dia)) {
    return json({ error: 'Falta el día (AAAA-MM-DD).' }, { status: 400 });
  }
  const r = await leerDiaPublicado({ cookies }, dia);
  if (r.error) {
    //  Sin datos nuevos la pantalla se queda con lo último que tenía: no se
    //  borra lo que se ve por un pedido que falló.
    return json({ error: 'No se pudo leer lo publicado.' }, { status: 502 });
  }
  return json({ publicado: r.publicado }, { headers: { 'cache-control': 'no-store' } });
}
