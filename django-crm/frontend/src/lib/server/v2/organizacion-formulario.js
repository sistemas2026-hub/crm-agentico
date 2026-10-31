/**
 * EL FORMULARIO → EL DOCUMENTO DE ORGANIZACIÓN.
 *
 * Vive aparte de `organizacion-config.js` por una razón que no es estética: esa
 * capa importa `$env/dynamic/private` para saber dónde está el motor, y el
 * harness de pruebas de este repositorio **no resuelve `$env/*`**. Una
 * traducción de formulario a documento no necesita saber dónde está el motor,
 * así que separarla la vuelve probable — y lo que no se puede probar acá es
 * justo el salto que más cuesta: el dato viaja bien y la capa servidor lo deja
 * caer o lo renombra. Ya pasó dos veces el 29/09/2026 con el backend en verde.
 *
 * NINGUNA REGLA DE COHERENCIA VIVE ACÁ. Las once —dos salas con el mismo
 * identificador, un área reclamada por dos departamentos, un agente sentado en
 * dos sitios— están en el esquema del motor, que valida el documento completo
 * antes de escribir. Esto hace FORMA: que los números sean números y que las
 * listas escritas con comas lleguen como listas.
 */

/**
 * Las ocupaciones que la pantalla NO edita, tal como viajaron en el campo
 * oculto.
 *
 * Un JSON roto se descarta entero en vez de propagarse: lo que llega mal es un
 * campo que el navegador reescribió, y guardar media lista sería peor que
 * guardar ninguna. El principal nunca sale de acá —ése lo pone el formulario—,
 * y si viniera repetido el documento tendría dos ocupaciones del mismo puesto,
 * que el esquema del motor rechaza con razón.
 */
function otrasOcupaciones(texto) {
  if (!texto) return [];
  try {
    const lista = JSON.parse(texto);
    if (!Array.isArray(lista)) return [];
    return lista
      .filter((o) => o && typeof o.puesto === 'string' && o.puesto !== 'principal')
      .map((o) => ({
        puesto: o.puesto,
        agente: typeof o.agente === 'string' ? o.agente : '',
        nombre: typeof o.nombre === 'string' ? o.nombre : ''
      }));
  } catch {
    return [];
  }
}

/** Una lista escrita con comas → un arreglo sin vacíos ni espacios sueltos. */
export function comasALista(texto) {
  return String(texto ?? '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

/**
 * El documento de organización que arma el formulario.
 *
 * Los campos llegan indexados (`dep:0:rotulo`) porque un formulario HTML es
 * plano y esto tiene tres listas anidadas. El índice es del formulario y no se
 * guarda: lo que identifica una sala es su `id`.
 *
 * Una fila SIN identificador se descarta entera. Es como se borra una: se
 * vacía su identificador. No hace falta un botón de borrar que mande otra
 * cosa, y así el formulario tiene un solo camino.
 *
 * @param {FormData} form
 */
export function organizacionDelFormulario(form) {
  const porPrefijo = (prefijo) => {
    const filas = new Map();
    for (const [clave, valor] of form.entries()) {
      const m = /^([a-z]+):(\d+):([a-z_]+)$/.exec(clave);
      if (!m || m[1] !== prefijo) continue;
      const i = Number(m[2]);
      if (!filas.has(i)) filas.set(i, {});
      filas.get(i)[m[3]] = String(valor ?? '').trim();
    }
    return [...filas.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
  };

  const pisos = porPrefijo('piso')
    .filter((p) => p.nivel !== '' && p.nivel != null)
    .map((p) => ({ nivel: Number(p.nivel), rotulo: p.rotulo || '' }));

  const departamentos = porPrefijo('dep')
    .filter((d) => d.id)
    .map((d) => ({
      id: d.id,
      rotulo: d.rotulo || d.id,
      direccion: d.direccion || '',
      piso: Number(d.piso || 1),
      plantilla: d.plantilla || '',
      areas: comasALista(d.areas),
      capacidades: comasALista(d.capacidades),
      //  EL PUESTO PRINCIPAL SE EDITA; LOS DEMÁS VIAJAN DE IDA Y VUELTA.
      //
      //  La pantalla sólo pregunta por el principal: declarar silla por silla
      //  sería pedirle a quien organiza la empresa que sepa cómo se llaman los
      //  puestos de una plantilla. Pero el documento se guarda ENTERO, así que
      //  mandar sólo el principal BORRA los otros.
      //
      //  Pasó, y se vio en el navegador: al agregar un departamento desde esta
      //  pantalla, Atención al Cliente perdió a su segundo agente y el pie
      //  pasó de «6 de 37 puestos ocupados» a «5 de 40». Sin error, sin aviso,
      //  y sólo visible contando.
      //
      //  Así que el formulario lleva los otros en un campo oculto y los
      //  devuelve tal cual. No se fusiona con lo que hay en la base: eso haría
      //  imposible quitar una ocupación, que es justo lo que un editor tiene
      //  que poder hacer.
      ocupaciones: [
        ...(d.agente ? [{ puesto: 'principal', agente: d.agente }] : []),
        ...otrasOcupaciones(d.otras)
      ],
      acento: d.acento || ''
    }));

  const espacios = porPrefijo('esp')
    .filter((e) => e.id)
    .map((e) => ({
      id: e.id,
      rotulo: e.rotulo || e.id,
      piso: Number(e.piso || 1),
      plantilla: e.plantilla || '',
      acento: e.acento || ''
    }));

  return { pisos, departamentos, espacios };
}
