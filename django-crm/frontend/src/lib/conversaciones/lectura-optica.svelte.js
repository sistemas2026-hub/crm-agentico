/**
 * La última lectura del equipo, recordada mientras dure la pantalla.
 *
 * POR QUÉ EXISTE
 * --------------
 * El panel de Equipo vive dentro de las pestañas de contexto, y cambiar de
 * pestaña lo DESMONTA: su estado local se pierde. Al volver, la medición ya
 * leída desaparecía y había que apretar «Consultar ahora» otra vez --incluso
 * habiéndola consultado hace diez segundos--. Reportado el 22/09/2026 mirando
 * la pantalla en producción.
 *
 * La lectura no se perdía por una regla de negocio: se perdía porque el
 * componente que la guardaba dejó de existir. Este módulo la saca de ahí.
 *
 * POR QUÉ NO ES UN CACHÉ, Y POR QUÉ NO VENCE
 * ------------------------------------------
 * El caché de verdad está en el motor, con su TTL de cinco minutos, y es el
 * que decide si hay que volver a preguntarle a SmartOLT. Esto es otra cosa:
 * es la memoria de lo que ESTA PANTALLA ya mostró. No vence por tiempo porque
 * no le hace falta -- cada valor se dibuja con su `leido_en`, así que una
 * medición vieja se ve vieja en vez de hacerse pasar por nueva. Esconderla a
 * los cinco minutos dejaría el panel en blanco sin que nadie lo pidiera, que
 * es exactamente el problema que esto viene a resolver.
 *
 * UNA SOLA RANURA, y a propósito: se mira una conversación a la vez. Guardar
 * un mapa por id crecería sin techo durante un turno de trabajo a cambio de
 * nada -- al volver a una conversación anterior, el `load` de la página trae
 * su lectura otra vez.
 */
let guardada = $state(/** @type {{ id: string, payload: any } | null} */ (null));

export const lecturaOptica = {
  /** Lo último que se mostró de ESA conversación, o null. */
  de(/** @type {string} */ id) {
    return guardada && guardada.id === id ? guardada.payload : null;
  },
  guardar(/** @type {string} */ id, /** @type {any} */ payload) {
    if (!id || !payload) return;
    guardada = { id, payload };
  }
};
