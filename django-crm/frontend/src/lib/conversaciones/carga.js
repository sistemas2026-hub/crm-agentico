/**
 * La carga de cada persona del equipo, para quien supervisa (29/10/2026).
 *
 * Sale de la cola que la pantalla YA tiene cargada: no hay consulta nueva.
 * Cuenta CONVERSACIONES abiertas asignadas, no chats: un chat con dos
 * abiertas de la misma persona es trabajo doble, y reasignar mueve
 * conversaciones (T4), no chats.
 *
 * El dueño es la asignación DURABLE de Dexter (`asignada_a_usuario_id`),
 * nunca el dueño del ticket del CRM (D28).
 */

/**
 * @param {any[]} cola  las filas de la cola, tal como las manda el motor
 * @param {number} ahora  epoch ms
 * @returns {{ usuario_id: string, nombre: string, abiertas: number,
 *             esperandoDesde: string|null, ids: string[] }[]}
 */
export function cargaPorOperador(cola, ahora = Date.now()) {
  /** @type {Map<string, any>} */
  const porPersona = new Map();
  for (const fila of cola || []) {
    for (const c of [fila, ...((fila && fila.abiertas) || [])]) {
      if (!c || c.estado === 'cerrada' || !c.asignada_a_usuario_id) continue;
      const id = String(c.asignada_a_usuario_id);
      const p = porPersona.get(id) ?? {
        usuario_id: id, nombre: c.asignada_a || 'Sin nombre', abiertas: 0,
        esperandoDesde: null, ids: []
      };
      if (p.ids.includes(c.id)) continue;
      p.abiertas += 1;
      p.ids.push(c.id);
      const desde = c.esperando_desde;
      if (desde && new Date(desde).getTime() <= ahora
          && (!p.esperandoDesde || new Date(desde) < new Date(p.esperandoDesde))) {
        p.esperandoDesde = desde;
      }
      porPersona.set(id, p);
    }
  }
  return [...porPersona.values()].sort(
    (a, b) => b.abiertas - a.abiertas || a.nombre.localeCompare(b.nombre, 'es')
  );
}
