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
 * traduce a areas. La paginacion de 25 no se toca: la pantalla sigue trayendo
 * una pagina, y los totales dejan de depender de cual.
 *
 * DE QUIEN ES EL AREA DE UN CASO  --  16/10/2026
 * ----------------------------------------------
 * Hasta hoy, de la PERSONA asignada: el CRM no tenia campo de area. Medido
 * en local ese dia: 65 casos con area `soporte_tecnico`, 64 en la pantalla.
 * El que faltaba estaba asignado a alguien sin area en el motor y caia en
 * "Sin área asignada". Y la consecuencia grave es la inversa: un ticket de
 * ventas asignado a un tecnico aparecia como Soporte Tecnico -- el mismo
 * defecto que el Supervisor NOC ya no tiene (cdaa9b27), vivo en esta
 * pantalla.
 *
 * Desde ese commit el caso trae su area escrita (`Case.area`, la que decide
 * `importacion_tickets.destinos`). `areaDelCaso` la lee PRIMERO y cae a la de
 * la persona solo cuando no esta escrita: los ~1.300 importados antes del
 * campo, que la reconciliacion va completando, y los casos cargados a mano
 * en el CRM. Es la misma asimetria del Supervisor: un caso CON area ajena no
 * es de soporte aunque lo tenga un tecnico; un caso SIN area sigue con el
 * criterio de ayer.
 *
 * POR QUE LA TRADUCCION PERSONA -> AREA SIGUE VIVIENDO ACA
 * --------------------------------------------------------
 * El mapa persona -> area no esta en el CRM: vive en
 * `asistente.area_colaborador` y lo sirve el motor (`/agentes/areas`). Django
 * cuenta lo que tiene --por area del caso y por responsable-- y quien conoce
 * las areas termina de sumar. Copiar el mapa al CRM crearia una segunda
 * verdad sobre el mismo dato.
 */

/** La categoria de los que no caen en ningun area del equipo. */
export const SIN_AREA = '__sin_area__';

/**
 * La cola entera, sin filtro de area (19/10/2026). Solo para quien administra:
 * un colaborador que la pida por la URL cae en su propia area, igual que con
 * cualquier otra. Hacia falta porque la pantalla solo mostraba un area a la
 * vez, y en produccion ningun ticket abierto trae el area escrita (794 de 794
 * vacios): todo dependia de a quien estaba asignado.
 */
export const TODAS_LAS_AREAS = '__todas__';

/** @typedef {{area?: string, assigned_to: string|null, total: number,
 *             urgentes: number, sin_respuesta: number, en_progreso: number}} FilaDesglose */

const VACIO = { total: 0, urgentes: 0, sin_respuesta: 0, sin_asignar: 0, en_progreso: 0 };

/**
 * El area de un caso: la escrita en el caso; si no la tiene, la de su
 * responsable; si tampoco, SIN_AREA.
 *
 * UNA sola funcion para la cola, las tarjetas y el detalle: las tres tienen
 * que decir lo mismo del mismo ticket, o un caso contaria en una tarjeta y
 * no apareceria al abrirla.
 *
 * @param {string|null|undefined} area  `Case.area`; vacia cuando no se sabe
 * @param {string|null|undefined} responsable  profile_id del asignado
 * @param {Record<string, string>} areaPorPersona  profile_id -> nombre de area
 * @returns {string}
 */
export function areaDelCaso(area, responsable, areaPorPersona = {}) {
  if (area) return area;
  return (responsable && areaPorPersona[responsable]) || SIN_AREA;
}

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
    //  El area escrita en el caso manda. Sin ella: sin responsable, o con uno
    //  que no pertenece a ningun area, los dos van a la misma categoria de
    //  excepcion, pero solo el primero cuenta como 'sin_asignar' -- tener
    //  responsable y que su area no este configurada es otro problema, y
    //  confundirlos esconde el que haya que arreglar.
    const area = areaDelCaso(fila?.area, persona, areaPorPersona);
    sumar(area, fila, persona === null);
  }

  //  Un area escrita en los casos que la configuracion no declara --la
  //  empresa la borro, o 'destinos' apunta a una que todavia no existe en
  //  /settings/areas-- se muestra con su nombre crudo en vez de esconderse:
  //  esos tickets existen y alguien los tiene que ver. Medido en local el
  //  16/10/2026: 3 casos con area 'ventas' y ninguna area 'ventas' declarada.
  const declaradas = new Set(areas.map((a) => a.nombre));
  const noDeclaradas = Object.keys(acumulado)
    .filter((n) => n !== SIN_AREA && !declaradas.has(n))
    .sort()
    .map((nombre) => ({ nombre, etiqueta: nombre, agentes: [] }));

  const filas = [...areas.map((a) => ({ ...a })),
                 ...noDeclaradas,
                 { nombre: SIN_AREA, etiqueta: 'Sin área asignada', agentes: [] }]
    .map((a) => ({ ...a, ...VACIO, ...(acumulado[a.nombre] ?? {}) }));

  //  Un area del equipo sin nada NO se esconde -- que este vacia es
  //  informacion. "Sin área asignada" si, cuando no hay ninguno: es una
  //  categoria de excepcion, no un area.
  return filas.filter((a) => a.nombre !== SIN_AREA || a.total > 0);
}

/**
 * Responsables cuyos tickets abiertos caen en "Sin área asignada".
 *
 * Solo cuentan las filas SIN area escrita en el caso: si el caso la trae, ya
 * esta en su tarjeta, y que la persona no tenga area configurada no esconde
 * nada. Sirve para avisar: esos tickets desaparecen de las columnas del
 * equipo y conviene que alguien lo sepa, en vez de que la cola parezca mas
 * corta de lo que es.
 *
 * @param {FilaDesglose[] | null | undefined} desglose
 * @param {Record<string, string>} areaPorPersona
 */
export function responsablesSinArea(desglose, areaPorPersona = {}) {
  if (!Array.isArray(desglose)) return [];
  return [...new Set(
    desglose
      .filter((f) => f?.assigned_to && !f.area && !areaPorPersona[f.assigned_to])
      .map((f) => f.assigned_to)
  )];
}


/**
 * Los responsables de un area, para pedirle al servidor su cola completa.
 *
 * EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 07/10/2026
 * ----------------------------------------------------------------
 * La pantalla pedia las 25 filas mas recientes de TODA la cola y recien
 * despues descartaba en el navegador las que no eran del area. Con 138
 * abiertos y las 25 mas recientes todas de cartera, Soporte Tecnico mostraba
 * la tabla VACIA mientras su cabecera decia 91.
 *
 * Hasta el 16/10/2026 esta lista viajaba como 'assigned_to', porque el area
 * se deducia de la persona. Hoy el API filtra por el area escrita en el caso
 * ('area') y esta lista viaja aparte ('area_responsables'), SOLO para los
 * casos que todavia no la tienen escrita: la mitad vieja del filtro, ver
 * areaDelCaso(). Una lista vacia significa que esa mitad no aplica, y el
 * filtro por area escrita sigue valiendo igual.
 *
 * @param {string} area  nombre interno del area, o '' / SIN_AREA
 * @param {Record<string, string>} areaPorPersona  profile_id -> area
 * @returns {string[]} ids de responsables, sin repetir
 */
export function responsablesDeArea(area, areaPorPersona = {}) {
  //  SIN_AREA no se puede pedir al servidor: son los casos sin area escrita
  //  y sin responsable, o con uno cuya area nadie configuro. Esa cola se
  //  sigue recortando del lado del navegador, y es su limite conocido.
  if (!area || area === SIN_AREA) return [];
  return [...new Set(
    Object.entries(areaPorPersona)
      .filter(([, suya]) => suya === area)
      .map(([persona]) => persona)
  )];
}
