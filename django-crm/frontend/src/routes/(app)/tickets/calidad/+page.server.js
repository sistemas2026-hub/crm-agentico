import { leerAreas } from '$lib/server/v2/areas.js';
import { leerResumenEncuestas } from '$lib/server/v2/encuestas.js';
import { diaEn, zonaDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';

/*
 * «Calidad de la atención» (28/10/2026). La ven quienes miran el trabajo de
 * todo el equipo: administración, supervisión y operaciones. Mide por persona, así que no
 * es para que cada colaborador compare la suya con la de los demás.
 *
 * ?dias= 7, 30 o 90 (por omisión 30), contados hasta HOY en la zona de la
 * empresa: el "hoy" del servidor en UTC se corre de día a las 7 p. m. de
 * Bogotá.
 */

const PUEDEN_VER = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);
const PERIODOS = [7, 30, 90];

/** @param {string} dia @param {number} n */
function restarDias(dia, n) {
  const d = new Date(`${dia}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals, fetch, cookies, url }) {
  const rol = /** @type {any} */ (locals)?.profile?.role;
  const pedido = Number(url.searchParams.get('dias'));
  const dias = PERIODOS.includes(pedido) ? pedido : 30;
  if (!PUEDEN_VER.has(rol)) return { puedeVer: false, dias, periodos: PERIODOS, resumen: null };

  const hasta = diaEn(await zonaDeLaEmpresa(locals, cookies));
  const desde = restarDias(hasta, dias - 1);
  const [resumen, { areas }] = await Promise.all([
    leerResumenEncuestas(locals, fetch, { desde, hasta }),
    leerAreas(locals, fetch)
  ]);
  return {
    puedeVer: true,
    dias,
    periodos: PERIODOS,
    desde,
    hasta,
    resumen,
    //  El nombre visible de cada área ('soporte_tecnico' -> 'Soporte técnico').
    etiquetasArea: Object.fromEntries(
      (areas ?? []).map((/** @type {any} */ a) => [a.nombre, a.etiqueta || a.nombre])
    )
  };
}
