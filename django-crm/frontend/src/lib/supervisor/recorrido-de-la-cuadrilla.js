/**
 * RECORRER LAS ÓRDENES DE UNA CUADRILLA DESDE SU CUADRO (07/11/2026).
 *
 * El usuario, sobre el Seguimiento: «agregá una flecha que tenga el nombre de
 * con qué sigue después de este ticket y al presionarla muestre la tarjeta de
 * la siguiente, y así hasta mostrar todos los tickets».
 *
 * El cuadro hablaba de UNA sola orden —la que la cuadrilla tiene en curso o,
 * si no hay, la que sigue— y las otras nueve no se veían desde ahí. Acá vive
 * la decisión de QUÉ orden se está mostrando; el componente solo la dibuja.
 *
 * POR QUÉ SE SIGUE UN NÚMERO DE OT Y NO UN ÍNDICE
 * ------------------------------------------------
 * Programación recarga sola cada 15 s. Si el recorrido guardara «voy en la
 * tercera», un reparto nuevo o una orden terminada correría la lista y el
 * cuadro saltaría a otra orden sin que nadie tocara nada — justo mientras
 * alguien la está leyendo. Guardar el NÚMERO lo vuelve estable: la orden
 * sigue siendo la misma aunque cambie de lugar, y si desaparece de la lista
 * el cuadro vuelve solo a lo que la cuadrilla está haciendo ahora.
 */

/**
 * El índice de la orden de la que habla el cuadro cuando nadie recorrió nada:
 * la que está en curso; si no hay, la marcada como siguiente; si tampoco, la
 * primera del día.
 *
 * @param {any[]} [ordenes] las órdenes de la cuadrilla, en el orden de la app
 * @param {number|null} [enCurso] el número de la OT en curso, si hay
 * @returns {number} el índice, o -1 si la cuadrilla no tiene órdenes
 */
export function indiceDelFoco(ordenes, enCurso = null) {
  const lista = ordenes ?? [];
  if (enCurso != null) {
    const i = lista.findIndex((o) => o?.numero === enCurso);
    if (i >= 0) return i;
  }
  const s = lista.findIndex((o) => o?.siguiente);
  if (s >= 0) return s;
  return lista.length ? 0 : -1;
}

/**
 * Dónde está parado el recorrido: qué orden se muestra, cuál es la de antes y
 * la de después, y si eso es lo que la cuadrilla hace ahora o algo que se está
 * mirando de más adelante.
 *
 * @param {any[]} [ordenes] las órdenes de la cuadrilla, en el orden de la app
 * @param {number|null} [enCurso] el número de la OT en curso, si hay
 * @param {number|null} [viendo] el número de la OT que se eligió mirar
 */
export function recorrido(ordenes, enCurso = null, viendo = null) {
  const lista = ordenes ?? [];
  const foco = indiceDelFoco(lista, enCurso);
  let i = foco;
  if (viendo != null) {
    const v = lista.findIndex((o) => o?.numero === viendo);
    //  La orden que se estaba mirando ya no está (la terminaron, la pasaron a
    //  otra cuadrilla): se vuelve a lo de ahora en vez de quedar en blanco.
    if (v >= 0) i = v;
  }
  return {
    orden: i >= 0 ? lista[i] : null,
    posicion: i >= 0 ? i + 1 : 0,
    total: lista.length,
    enElFoco: i === foco,
    anterior: i > 0 ? lista[i - 1] : null,
    siguiente: i >= 0 && i + 1 < lista.length ? lista[i + 1] : null
  };
}

/**
 * La línea de arriba del cuadro: de qué habla lo que se está viendo.
 *
 * MIENTRAS SE RECORRE, EL TÍTULO HABLA DE LA ORDEN QUE SE MUESTRA, no de lo
 * que la cuadrilla hace ahora. Escribir «En sitio · OT #12» encima de la
 * dirección de la #21 es el mismo error que se arregló el 30/10/2026 al revés
 * («el asunto de ESA orden, no de la que sigue»), y es peor acá: el cuadro
 * sirve para decidir a quién llamar.
 *
 * @param {any} resumen el `resumen_del_dia` de la cuadrilla
 * @param {ReturnType<typeof recorrido>} paso dónde está parado el recorrido
 * @returns {string}
 */
export function tituloDel(resumen, paso) {
  const r = resumen ?? {};
  const o = paso?.orden ?? null;
  if (o && paso && !paso.enElFoco) {
    return o.estado_texto ? `${o.estado_texto} · OT #${o.numero}` : `OT #${o.numero}`;
  }
  const c = r.en_curso;
  if (c) return `${c.estado === 'en_sitio' ? 'En sitio' : 'En camino'} · OT #${c.numero}`;
  if (r.hechas && r.hechas === r.total) return 'Terminó el día';
  //  Solo la MARCADA como siguiente se anuncia así. Si no hay ninguna activa
  //  —todo terminado o cancelado— el recorrido igual arranca en la primera
  //  para poder recorrer, pero el título no puede decir que la cuadrilla
  //  «sigue» por una orden que ya pasó.
  if (o?.siguiente) return `${r.salio ? 'Sigue' : 'Empieza por'} OT #${o.numero}`;
  return r.salio ? 'Entre órdenes' : 'Todavía no sale';
}

/**
 * El nombre con el que se anuncia una orden en la flecha. El número solo no
 * alcanza: «OT #167» no dice si vale la pena abrirla, y el asunto sí.
 *
 * @param {any} orden
 * @returns {string}
 */
export function nombreDeLaOrden(orden) {
  if (!orden) return '';
  const asunto = (orden.asunto || orden.tipo || '').trim();
  return asunto ? `OT #${orden.numero} · ${asunto}` : `OT #${orden.numero}`;
}
