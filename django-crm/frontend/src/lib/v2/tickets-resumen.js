/**
 * EL RESUMEN DE LA COLA POR AREA
 * ===============================
 *
 * EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 06/10/2026
 * ----------------------------------------------------------------
 * La pantalla mostraba:
 *
 *     Tickets: 47 · Cartera: 0 · Soporte Técnico: 25 · Administración: 0
 *
 * y parecia que 22 tickets no tenian area. No era eso: el total venia del
 * SERVIDOR (`cases_count`, sobre los 47 abiertos) y el desglose se calculaba
 * en el NAVEGADOR sobre `results`, que es una pagina de 25. Los 22 que
 * "faltaban" eran los que no habian llegado.
 *
 * Medido ese dia: los 47 abiertos tenian exactamente un responsable, la misma
 * persona, con area `soporte_tecnico`. O sea que el desglose correcto era
 * 47/0/0, no 25/0/0.
 *
 * QUE CAMBIA
 * ----------
 * El desglose ya no se deriva de las filas visibles. El backend devuelve
 * `open_by_assignee` --un GROUP BY sobre TODOS los abiertos-- y aqui se
 * traduce de responsable a area. La paginacion de 25 no se toca: la pantalla
 * sigue trayendo una pagina, y los totales dejan de depender de cual.
 *
 * POR QUE LA TRADUCCION VIVE ACA Y NO EN EL BACKEND
 * -------------------------------------------------
 * El mapa persona -> area no esta en el CRM: vive en
 * `asistente.area_colaborador` y lo sirve el motor (`/agentes/areas`). Django
 * cuenta lo que tiene; quien conoce las areas suma. Copiar el mapa al CRM
 * crearia una segunda verdad sobre el mismo dato.
 */

/** La categoria de los que no caen en ningun area del equipo. */
export const SIN_AREA = '__sin_area__';

/** @typedef {{assigned_to: string|null, total: number, urgentes: number,
 *             sin_respuesta: number, en_progreso: number}} FilaDesglose */

const VACIO = { total: 0, urgentes: 0, sin_respuesta: 0, sin_asignar: 0, en_progreso: 0 };

/**
 * La cola por area, sobre el conjunto COMPLETO.
 *
 * Devuelve `null` si el desglose no vino -- un backend viejo, o una respuesta
 * que fallo. `null` no es lo mismo que "todas las areas en cero", y quien lo
 * reciba tiene que poder distinguirlo: mostrar ceros cuando no se pudo
 * contar es exactamente el error que este modulo existe para no repetir.
 *
 * @param {FilaDesglose[] | null | undefined} desglose  `open_by_assignee` del backend
 * @param {{nombre: string, etiqueta?: string}[]} areas  las areas del equipo
 * @param {Record<string, string>} areaPorPersona  profile_id -> nombre de area
 * @returns {any[] | null}
 */
export function resumenPorArea(desglose, areas, areaPorPersona = {}) {
  if (!Array.isArray(desglose)) return null;

  /** @type {Record<string, any>} */
  const acumulado = {};
  const sumar = (clave, fila, sinAsignar) => {
    const a = (acumulado[clave] ??= { ...VACIO });
    a.total += fila.total ?? 0;
    a.urgentes += fila.urgentes ?? 0;
    a.sin_respuesta += fila.sin_respuesta ?? 0;
    a.en_progreso += fila.en_progreso ?? 0;
    if (sinAsignar) a.sin_asignar += fila.total ?? 0;
  };

  for (const fila of desglose) {
    const persona = fila?.assigned_to ?? null;
    //  Sin responsable, o con uno que no pertenece a ningun area: los dos van
    //  a la misma categoria de excepcion, pero solo el primero cuenta como
    //  'sin_asignar' -- tener responsable y que su area no este configurada es
    //  otro problema, y confundirlos esconde el que haya que arreglar.
    const area = persona ? (areaPorPersona[persona] || SIN_AREA) : SIN_AREA;
    sumar(area, fila, persona === null);
  }

  const filas = [...areas.map((a) => ({ ...a })),
                 { nombre: SIN_AREA, etiqueta: 'Sin área asignada', agentes: [] }]
    .map((a) => ({ ...a, ...VACIO, ...(acumulado[a.nombre] ?? {}) }));

  //  Un area del equipo sin nada NO se esconde -- que este vacia es
  //  informacion. "Sin área asignada" si, cuando no hay ninguno: es una
  //  categoria de excepcion, no un area.
  return filas.filter((a) => a.nombre !== SIN_AREA || a.total > 0);
}

/**
 * Lo que el desglose deja afuera de las areas conocidas.
 *
 * Sirve para avisar: si hay responsables sin area configurada, sus tickets
 * desaparecen de las columnas del equipo y conviene que alguien lo sepa, en
 * vez de que la cola parezca mas corta de lo que es.
 *
 * @param {FilaDesglose[] | null | undefined} desglose
 * @param {Record<string, string>} areaPorPersona
 */
export function responsablesSinArea(desglose, areaPorPersona = {}) {
  if (!Array.isArray(desglose)) return [];
  return [...new Set(
    desglose
      .filter((f) => f?.assigned_to && !areaPorPersona[f.assigned_to])
      .map((f) => f.assigned_to)
  )];
}


/**
 * Los responsables de un area, para poder pedirle al servidor SOLO su cola.
 *
 * EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 07/10/2026
 * ----------------------------------------------------------------
 * El area no es un campo del CRM: es una propiedad de la persona asignada.
 * La pantalla pedia las 25 filas mas recientes de TODA la cola y recien
 * despues descartaba en el navegador las que no eran del area. Con 138
 * abiertos y las 25 mas recientes todas de cartera, Soporte Tecnico mostraba
 * la tabla VACIA mientras su cabecera decia 91.
 *
 * Traducir el area a sus responsables permite mandar 'assigned_to' al API, y
 * entonces la pagina que llega ya es la del area. Subir el limite no era la
 * solucion: con mil tickets el problema vuelve, solo mas tarde.
 *
 * Devuelve lista vacia cuando el area no tiene gente, y quien llama NO debe
 * mandar el filtro en ese caso: un 'assigned_to' vacio no filtra nada y
 * traeria la cola entera, que es justo lo que se quiere evitar.
 *
 * @param {string} area  nombre interno del area, o '' / SIN_AREA
 * @param {Record<string, string>} areaPorPersona  profile_id -> area
 * @returns {string[]} ids de responsables, sin repetir
 */
export function responsablesDeArea(area, areaPorPersona = {}) {
  //  SIN_AREA no se puede pedir por 'assigned_to': son los casos sin
  //  responsable, o con uno cuya area nadie configuro. Esa cola se sigue
  //  recortando del lado del navegador, y es su limite conocido.
  if (!area || area === SIN_AREA) return [];
  return [...new Set(
    Object.entries(areaPorPersona)
      .filter(([, suya]) => suya === area)
      .map(([persona]) => persona)
  )];
}
