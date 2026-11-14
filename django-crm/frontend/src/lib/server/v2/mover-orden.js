/**
 * MOVER UNA ORDEN DE UN TÉCNICO A OTRO  --  14/11/2026
 *
 * POR QUÉ `/mover/` Y NO `/asignar/`
 * ----------------------------------
 * El primer intento llamaba a `AsignarTrabajoView`, que es el endpoint que
 * «parece» el correcto y no lo es: pone al nuevo como principal y le DEJA la
 * fila en `asignaciones` al anterior (`campo/services/despacho.py:217`). Y
 * toda la autorización intra-tenant de campo mide pertenencia a
 * `asignaciones`, nunca `es_principal` (`campo/views.py:88`,
 * `campo/services/transiciones.py:140`).
 *
 * Medido el 14/11/2026 contra Postgres real: después de «mover» la orden a B,
 * el técnico A la marcó en camino, en sitio y la COMPLETÓ, y la bitácora
 * quedó con `trabajo_completado_campo` a nombre de A sobre una orden cuyo
 * principal es B. Dos personas escribiendo sobre el mismo trabajo.
 *
 * `/mover/` (`campo/despacho_views.py::MoverLaOrdenView`) hace las dos cosas
 * bajo la misma fila bloqueada: sube al nuevo y borra la fila del anterior.
 *
 * SIN `Idempotency-Key`, y no es un olvido: la cabecera es opcional
 * (`campo/services/idempotencia.py:154`) y la garantía está más abajo y es
 * más fuerte. `mover_la_orden` relee bajo `select_for_update` y, si el
 * destino ya es el responsable, sale sin tocar nada. Eso cubre el doble clic
 * y además el caso que una clave no cubriría: dos personas moviendo la misma
 * orden al mismo técnico desde dos sesiones distintas.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * @param {{ cookies: any }} ctx
 * @param {{ orden: string, profile: string, motivo: string }} d
 * @returns {Promise<{resultado?: string, aviso?: boolean}>}
 */
export async function moverOrden(ctx, { orden, profile, motivo }) {
  const id = encodeURIComponent(orden);
  return await apiRequest(`/campo/trabajos/${id}/mover/`, {
    method: 'POST',
    body: { profile_id: profile, motivo }
  }, ctx);
}
