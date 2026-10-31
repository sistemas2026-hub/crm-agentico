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
 * Las ocupaciones de puestos que la plantilla elegida NO tiene, tal como
 * viajaron en el campo oculto.
 *
 * Existen: la empresa pudo declarar un puesto y después cambiar la sala por
 * una que no lo tiene. El motor lo reporta como «puesto desconocido» en vez de
 * ignorarlo, así que descartarlo acá convertiría un aviso en una desaparición.
 *
 * Un JSON roto se descarta entero en vez de propagarse: lo que llega mal es un
 * campo que el navegador reescribió, y guardar media lista sería peor que
 * guardar ninguna.
 */
function ocupacionesOcultas(texto) {
  if (!texto) return [];
  try {
    const lista = JSON.parse(texto);
    if (!Array.isArray(lista)) return [];
    return lista
      .filter((o) => o && typeof o.puesto === 'string' && o.puesto)
      .map((o) => ({
        puesto: o.puesto,
        agente: typeof o.agente === 'string' ? o.agente : '',
        nombre: typeof o.nombre === 'string' ? o.nombre : ''
      }));
  } catch {
    return [];
  }
}

/**
 * QUIÉN SE SIENTA EN CADA SILLA, UNA POR UNA.
 *
 * El formulario manda un campo por puesto de la plantilla elegida
 * (`ocupa_principal`, `ocupa_p1`, …) y este traductor NO sabe qué puestos
 * tiene cada plantilla: lee los que vengan. Esa ignorancia es a propósito —la
 * geometría de una sala vive en el catálogo del frontend, y duplicar acá qué
 * sillas tiene cada plantilla sería una segunda verdad que se separa el día
 * que alguien agregue un escritorio.
 *
 * Un puesto vacío NO se guarda: «ninguno» es la ausencia de la ocupación, no
 * una ocupación con agente vacío. Guardarla haría que un puesto libre y uno
 * que alguien vació se vieran distintos en la configuración sin serlo.
 *
 * Y UN PUESTO NO PUEDE VENIR DOS VECES. El esquema del motor rechaza dos
 * ocupaciones del mismo puesto, con razón: no se sabría cuál manda. Lo que
 * está en pantalla gana sobre lo que viajó oculto, porque es lo que alguien
 * acaba de mirar.
 */
function ocupacionesDe(campos) {
  const enPantalla = Object.entries(campos)
    .filter(([clave, valor]) => clave.startsWith('ocupa_') && valor)
    .map(([clave, valor]) => ({ puesto: clave.slice('ocupa_'.length), agente: valor }));

  const declarados = new Set(enPantalla.map((o) => o.puesto));
  return [
    ...enPantalla,
    ...ocupacionesOcultas(campos.otras).filter((o) => !declarados.has(o.puesto))
  ];
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
      //  `[a-z0-9_]` y no `[a-z_]`: los puestos de una plantilla se llaman
      //  `p1`, `p2`, `p3`, asi que `ocupa_p1` no entraria y la silla se
      //  guardaria vacia sin que nada lo dijera.
      const m = /^([a-z]+):(\d+):([a-z0-9_]+)$/.exec(clave);
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
      ocupaciones: ocupacionesDe(d),
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
