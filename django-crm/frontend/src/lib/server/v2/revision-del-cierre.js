import { apiRequest } from '$lib/api-helpers.js';

/**
 * Lo que una persona confirma de la revisión del Supervisor (30/10/2026,
 * SPEC/objetivos/revision-del-cierre.md). El Supervisor indica; esto lo
 * ejecuta quien gestiona, con su sesión.
 *
 * La `Idempotency-Key` va armada con la orden y su vuelta: un doble clic, o un
 * reintento de red, es la misma decisión y el backend la aplica una vez. Una
 * vuelta nueva (después de una devolución) es otra decisión.
 */

/**
 * Aprueba y cierra. Son dos pasos del backend a propósito —aprobar dice que el
 * trabajo está bien hecho (y cierra el ticket del ISP), cerrar lo saca de la
 * operación— y van juntos porque eso es lo que la persona decidió con un toque.
 *
 * @param {{ cookies: any }} ctx
 * @param {{ orden: string, vuelta: string | number, observacion?: string }} d
 */
export async function aprobarYCerrar(ctx, { orden, vuelta, observacion = '' }) {
  const id = encodeURIComponent(orden);
  const validada = await apiRequest(`/campo/trabajos/${id}/validar/`, {
    method: 'POST',
    body: { decision: 'aprobar', observacion },
    headers: { 'Idempotency-Key': `aprobar|${orden}|${vuelta}` }
  }, ctx);
  await apiRequest(`/campo/trabajos/${id}/cerrar/`, {
    method: 'POST',
    body: { observacion },
    headers: { 'Idempotency-Key': `cerrar|${orden}|${vuelta}` }
  }, ctx);
  return { ticketIsp: validada?.ticket_isp ?? null };
}

/**
 * Cierra una orden que ya estaba APROBADA y quedó sin cerrar (30/10/2026: la
 * OT #3 en producción). Solo el cierre: la aprobación ya se hizo.
 *
 * @param {{ cookies: any }} ctx
 * @param {{ orden: string, vuelta: string | number }} d
 */
export async function cerrarAprobada(ctx, { orden, vuelta }) {
  return apiRequest(`/campo/trabajos/${encodeURIComponent(orden)}/cerrar/`, {
    method: 'POST',
    body: { observacion: 'Cerrada en Programación: estaba aprobada.' },
    headers: { 'Idempotency-Key': `cerrar|${orden}|${vuelta}` }
  }, ctx);
}

/**
 * Devuelve el trabajo al técnico: qué evidencia rehacer y por qué. Al técnico
 * le llega el aviso que ya existe (`avisos.avisar_devolucion`).
 *
 * @param {{ cookies: any }} ctx
 * @param {{ orden: string, vuelta: string | number, requisitos: string[], observacion: string }} d
 */
export async function devolverAlTecnico(ctx, { orden, vuelta, requisitos, observacion }) {
  return apiRequest(`/campo/trabajos/${encodeURIComponent(orden)}/validar/`, {
    method: 'POST',
    body: { decision: 'requerir_correccion', requisitos_a_corregir: requisitos, observacion },
    headers: { 'Idempotency-Key': `devolver|${orden}|${vuelta}` }
  }, ctx);
}
