import { env } from '$env/dynamic/private';
import { headersMotor } from '$lib/server/v2/motor-headers.js';

/**
 * Las áreas de la empresa y de qué área es cada persona.
 *
 * El CRM no tiene campo de área: el área vive en el asistente y es POR
 * PERSONA, así que la de un caso se deriva de a quién está asignado. Esto lo
 * usan la cola de tickets (para agrupar) y el detalle (para el panel
 * lateral) -- una sola función porque las dos pantallas tienen que agrupar
 * igual, o dirían cosas distintas del mismo ticket.
 *
 * Devuelve `{ areas: [], areaPorPersona: {} }` si el asistente no responde:
 * ver los tickets no puede depender de que el motor esté arriba.
 *
 * @param {typeof globalThis.fetch} fetch
 * @returns {Promise<{ areas: any[], areaPorPersona: Record<string, string> }>}
 */
export async function leerAreas(fetch) {
  const base = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!base || !tenant) return { areas: [], areaPorPersona: {} };

  const t = encodeURIComponent(tenant);
  // '/agentes/areas' es el liviano: sólo lecturas locales del asistente.
  // '/agentes/asignaciones' devuelve lo mismo y además identidades, agentes y
  // los candidatos del sistema externo -- una llamada HTTP afuera que estas
  // pantallas no usan y que igual esperaban (segundos, con la pantalla
  // quieta).
  //
  // Se prueba el liviano y se cae al viejo si todavía no existe: el motor y
  // esta pantalla se despliegan por separado, así que hay una ventana en la
  // que ya está el frontend nuevo y todavía no el motor nuevo. Sin esta
  // caída, en esa ventana TODOS los tickets aparecerían sin área -- y a un
  // colaborador, que sólo ve la suya, no le aparecería ninguno.
  for (const ruta of ['/agentes/areas', '/agentes/asignaciones']) {
    try {
      const r = await fetch(`${base}${ruta}?tenant=${t}`, {
        headers: headersMotor(),
        // El plazo importa tanto como el endpoint: sin él, un motor lento
        // deja la cola en blanco todo ese rato. La pantalla ya sabe seguir
        // sin áreas; lo que no sabía era dejar de esperarlas.
        signal: AbortSignal.timeout(5000)
      });
      if (r.status === 404) continue;
      if (!r.ok) return { areas: [], areaPorPersona: {} };
      const d = await r.json();
      return { areas: d.areas ?? [], areaPorPersona: d.areas_por_persona ?? {} };
    } catch {
      return { areas: [], areaPorPersona: {} };
    }
  }
  return { areas: [], areaPorPersona: {} };
}
