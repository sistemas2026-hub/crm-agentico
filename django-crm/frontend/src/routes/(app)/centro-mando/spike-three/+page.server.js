import { redirect } from '@sveltejs/kit';
import { load as cargaDelCentro } from '../+page.server.js';

/**
 * EL SPIKE COME DEL MISMO PLATO.
 *
 * La carga es literalmente la de `/centro-mando`, reusada y no copiada: si el
 * prototipo leyera los datos por su cuenta, la comparación mediría dos
 * lecturas distintas y no dos motores. Y una copia se desincronizaría el día
 * que la original cambie, que es cuando la comparación dejaría de valer sin
 * que nadie se entere.
 *
 * SOLO ADMIN, EN EL SERVIDOR  --  12/11/2026
 * Es un prototipo de Three.js con datos reales de la empresa y sin decisión
 * tomada (Pixi o Three: pendiente, auditoría del menú §4 ítem 14). Hasta hoy
 * lo abría cualquiera que supiera la URL. No se borra: es la evidencia para
 * decidir. Quien no es ADMIN vuelve al centro de mando.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load(event) {
  if (event.locals.profile?.role !== 'ADMIN') redirect(303, '/centro-mando');
  return cargaDelCentro(event);
}
