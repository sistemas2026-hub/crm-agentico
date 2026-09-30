/**
 * Programación — Supervisor NOC IA: los datos de /supervisor-noc/programacion.
 *
 * Server-only, y hermano de `supervisor-noc.js`: reusa su `traducirError` en
 * vez de repetir la traduccion de status, y pasa por el mismo `apiRequest`.
 * No hay un segundo cliente HTTP.
 *
 * LO QUE ESTA CAPA NO HACE
 * No calcula capacidad. 'operaciones/capacidad.py' la deriva cuando se
 * pregunta -- a proposito, porque un numero guardado queda viejo en cuanto
 * cambia cualquiera de las cinco cosas de las que depende -- y viene con su
 * riesgo y sus 'faltantes'. Rederivarla aca seria una segunda verdad.
 *
 * Y no ejecuta nada: ni WispHub, ni SmartOLT, ni despacho. Las dos escrituras
 * que expone (secuenciar y publicar) mueven ORDEN PROPUESTO y ESTADO DE PLAN,
 * nunca una orden ni una asignacion.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { traducirError } from './supervisor-noc.js';

/**
 * La jornada de un dia: sus lineas en orden reproducible, mas el resumen que
 * cuenta los empates en vez de resolverlos.
 *
 * EXIGE UN DIA. El backend responde 400 FALTA_FILTRO sin 'dia' ni 'plan', con
 * un motivo que vale la pena respetar: "sin filtro, 'la jornada' no significa
 * nada". Por eso la pantalla abre con una fecha, nunca con "todo".
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} dia  YYYY-MM-DD
 */
export async function leerJornada({ cookies }, dia) {
  try {
    const d = await apiRequest(
      `/operaciones/programacion/jornada/?dia=${encodeURIComponent(dia)}`,
      {},
      { cookies }
    );
    return {
      count: d?.count ?? 0,
      lineas: d?.resultados ?? [],
      resumen: d?.resumen ?? null,
      filtro: d?.filtro ?? null,
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { count: null, lineas: [], resumen: null, filtro: null, error: traducirError(err, 'la jornada') };
  }
}

/**
 * La capacidad operacional del dia, POR PERSONA.
 *
 * NO HAY CUADRILLAS CON NOMBRE en el backend, y no es un olvido:
 * 'capacidad.py' lo dice ("no existe una regla empresarial de productividad
 * de cuadrillas, y no se inventa una aqui"). Lo que existe es
 * 'campo.AsignacionTrabajo', que ata PERSONAS a una orden. Asi que esta
 * funcion devuelve personas, y la pantalla muestra personas.
 *
 * Cada una trae su jornada, su disponibilidad, la carga comprometida, lo que
 * le queda, su 'riesgo' y los 'faltantes' -- si falta la duracion de alguna
 * orden, el riesgo responde INDETERMINADO en vez de "sin sobrecarga". Un dato
 * que falta no vale cero.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} dia  YYYY-MM-DD
 */
export async function leerCapacidad({ cookies }, dia) {
  try {
    const d = await apiRequest(
      `/operaciones/capacidad/jornada/?dia=${encodeURIComponent(dia)}`,
      {},
      { cookies }
    );
    return {
      jornada: d?.jornada ?? null,
      personas: d?.resultados ?? d?.personas_detalle ?? [],
      total_personas: d?.personas ?? null,
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { jornada: null, personas: [], total_personas: null, error: traducirError(err, 'la capacidad de la jornada') };
  }
}

/**
 * Las propuestas del Supervisor que hablan de programacion.
 *
 * Son las mismas propuestas de la otra pantalla, acotadas a las señales del
 * dominio: el backend no tiene un endpoint "recomendaciones de programacion",
 * y fabricar uno duplicaria la cola que ya existe.
 */
export const SENALES_PROGRAMACION = [
  'orden_sin_programar',
  'programacion_sin_publicar',
  'orden_con_riesgo_operacional',
  'orden_sla_vencido',
  'orden_sla_por_vencer',
  'dato_incompleto'
];

/**
 * Reordena la jornada entera en UNA transaccion.
 *
 * NO REPROGRAMA: no toca 'programada_para', ni el dia, ni el plan, ni la
 * asignacion. Solo el orden propuesto (operaciones/views.py).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {Record<string, any>} cuerpo
 */
export async function secuenciarJornada({ cookies }, cuerpo) {
  return apiRequest(
    '/operaciones/programacion/jornada/secuenciar/',
    { method: 'POST', body: cuerpo },
    { cookies }
  );
}

/**
 * Publica un plan semanal: borrador -> publicada, y nada mas. No ejecuta la
 * programacion ni toca ninguna orden.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} programacionId
 */
export async function publicarProgramacion({ cookies }, programacionId) {
  return apiRequest(
    `/operaciones/programacion/${programacionId}/publicar/`,
    { method: 'POST', body: {} },
    { cookies }
  );
}

/**
 * Los cuatro numeros de la cabecera, derivados de lo que ya llego.
 *
 * SIN INVENTAR NINGUNO. Cada uno sale de contar las lineas que el backend
 * devolvio, o se declara ausente. El porcentaje de capacidad es el unico que
 * no se cuenta aca: lo trae 'capacidad.py' por persona, y si alguna tiene
 * riesgo INDETERMINADO el promedio se marca parcial en vez de presentarse
 * como si fuera de todos.
 *
 * @param {{ lineas: any[], count: number|null, error: any }} jornada
 * @param {{ personas: any[], error: any }} capacidad
 */
export function resumenProgramacion(jornada, capacidad) {
  /** Un sobre que declara ausencia. Igual que en supervisor-noc.js. */
  const sinDato = (/** @type {string} */ motivo) => ({
    estado: 'SIN_DATO',
    valor: null,
    motivo
  });
  const valido = (/** @type {number} */ v) => ({ estado: 'VALIDO', valor: v, motivo: '' });

  const hayJornada = !jornada.error && Array.isArray(jornada.lineas);
  const lineas = hayJornada ? jornada.lineas : [];

  // 'secuencia = 0' significa SIN SECUENCIAR (decision E-2 del backend), no
  // "primera". Contarla como orden ya secuenciada seria leer al reves el
  // unico campo que esa decision fijo.
  const sinSecuenciar = lineas.filter((/** @type {any} */ l) => (l.secuencia ?? 0) === 0).length;
  const bloqueadas = lineas.filter((/** @type {any} */ l) => l.estado === 'bloqueada').length;

  const personas = capacidad.error ? [] : capacidad.personas;
  const conRiesgo = personas.filter(
    (/** @type {any} */ p) => p?.riesgo?.estado === 'SOBRECARGA' || p?.riesgo === 'SOBRECARGA'
  ).length;

  // El % de ocupacion: carga conocida sobre jornada, promediado entre las
  // personas que tienen los dos datos. Si a alguna le faltan duraciones, el
  // promedio se declara parcial -- no se imputa nada.
  let ocupacion = sinDato('El backend no entregó la capacidad de la jornada.');
  if (!capacidad.error && personas.length) {
    const utiles = personas.filter(
      (/** @type {any} */ p) => p?.jornada?.minutos > 0 && p?.carga?.minutos_conocidos != null
    );
    if (utiles.length) {
      const pct =
        utiles.reduce(
          (/** @type {number} */ t, /** @type {any} */ p) =>
            t + p.carga.minutos_conocidos / p.jornada.minutos,
          0
        ) / utiles.length;
      const completos = utiles.every((/** @type {any} */ p) => (p.faltantes ?? []).length === 0);
      ocupacion = {
        estado: completos ? 'VALIDO' : 'DATOS_INSUFICIENTES',
        valor: Math.round(pct * 100),
        motivo: completos
          ? ''
          : 'Alguna orden no declara duración: el porcentaje se calculó sobre lo conocido.'
      };
    }
  }

  return [
    {
      clave: 'ordenes',
      titulo: 'Órdenes en la jornada',
      dato: hayJornada ? valido(jornada.count ?? lineas.length) : sinDato('No se pudo leer la jornada.')
    },
    {
      clave: 'sin_secuenciar',
      titulo: 'Sin secuenciar',
      dato: hayJornada ? valido(sinSecuenciar) : sinDato('No se pudo leer la jornada.')
    },
    { clave: 'ocupacion', titulo: 'Ocupación media', dato: ocupacion, sufijo: '%' },
    {
      clave: 'bloqueadas',
      titulo: 'Bloqueadas',
      dato: hayJornada ? valido(bloqueadas) : sinDato('No se pudo leer la jornada.')
    },
    {
      clave: 'sobrecarga',
      titulo: 'Personas en sobrecarga',
      dato: capacidad.error ? sinDato('No se pudo leer la capacidad.') : valido(conRiesgo)
    }
  ];
}

/**
 * Las causas del catalogo CERRADO de NovedadOperativa que tienen sentido al
 * reprogramar o reordenar. No es una lista nueva: son las mismas claves que
 * 'operaciones/models.py' declara, y el servicio las valida del otro lado.
 * Se repiten aca solo para poder ofrecerlas en un selector -- si divergen,
 * gana el backend, que rechaza la que no conozca.
 */
export const CAUSAS = [
  { valor: 'reprogramacion', texto: 'Reprogramación' },
  { valor: 'cambio_de_prioridad', texto: 'Cambio de prioridad' },
  { valor: 'ausencia', texto: 'Ausencia' },
  { valor: 'bloqueo', texto: 'Bloqueo' },
  { valor: 'falta_material', texto: 'Falta de material' },
  { valor: 'dependencia', texto: 'Dependencia pendiente' },
  { valor: 'dato_incompleto', texto: 'Dato incompleto' }
];

/**
 * El detalle de una orden de trabajo, RECORTADO.
 *
 * 'OrdenTrabajoDetailSerializer' esta pensado para que un tecnico descargue la
 * orden y trabaje sin señal: devuelve el cliente completo, con telefono y
 * coordenadas GPS. Esta es una consola de PROGRAMACION -- para decidir cuando
 * y con quien va una visita hacen falta el nombre y la direccion, no el
 * telefono del cliente ni su punto exacto en el mapa.
 *
 * Asi que el recorte se hace del lado del servidor, no ocultando campos en la
 * pantalla: lo que no se necesita no viaja al navegador. Mismo criterio que
 * las listas blancas del motor.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 */
export async function leerOrden({ cookies }, ordenId) {
  try {
    const d = await apiRequest(`/campo/trabajos/${ordenId}/`, {}, { cookies });
    return {
      datos: {
        id: d?.id,
        numero: d?.numero,
        revision: d?.revision,
        tipo: d?.tipo ?? null,
        // Solo nombre y direccion. 'telefono', 'lat' y 'lng' se descartan aca.
        cliente: { nombre: d?.cliente?.nombre ?? null, direccion: d?.cliente?.direccion ?? null },
        tecnico_principal: d?.tecnico_principal ?? null,
        cuadrilla: d?.cuadrilla ?? [],
        diagnostico_previo: d?.diagnostico_previo ?? null,
        estado_operativo: d?.estado_operativo ?? null,
        estado_validacion: d?.estado_validacion ?? null,
        programada_para: d?.programada_para ?? null,
        iniciada_en: d?.iniciada_en ?? null,
        completada_campo_en: d?.completada_campo_en ?? null,
        created_at: d?.created_at ?? null,
        updated_at: d?.updated_at ?? null,
        n_evidencias: Array.isArray(d?.evidencias) ? d.evidencias.length : null
      },
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'esta orden de trabajo') };
  }
}

/**
 * La carga de UNA persona en un dia.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} dia
 * @param {string} profileId
 */
export async function leerCargaPersona({ cookies }, dia, profileId) {
  try {
    const d = await apiRequest(
      `/operaciones/capacidad/jornada/?dia=${encodeURIComponent(dia)}&profile_id=${encodeURIComponent(profileId)}`,
      {},
      { cookies }
    );
    return { datos: d, error: null };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'la carga de esta persona') };
  }
}

/**
 * Reprograma una orden que YA esta en un plan.
 *
 * El 'programacion_semanal_id' NO se inventa ni se busca: sale de la linea de
 * la jornada, que ya lo trae. Una orden sin plan no se puede reprogramar desde
 * aca -- haria falta elegir plan, y no existe ningun endpoint que los liste.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 * @param {{ programacion_semanal_id: string, programada_para: string, causa?: string, motivo?: string }} cuerpo
 */
export async function reprogramarOrden({ cookies }, ordenId, cuerpo) {
  return apiRequest(
    `/campo/trabajos/${ordenId}/reprogramar/`,
    { method: 'POST', body: cuerpo },
    { cookies }
  );
}

/**
 * Cambia el orden propuesto de UNA linea.
 *
 * NO REPROGRAMA: el propio backend lo dice ("cambiar la secuencia no es
 * reprogramar"). No toca 'programada_para', ni el dia, ni el plan, ni ninguna
 * otra linea -- por eso su serializer declara 'secuencia' y nada mas.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} lineaId
 * @param {{ secuencia: number, causa?: string, motivo?: string }} cuerpo
 */
export async function cambiarSecuencia({ cookies }, lineaId, cuerpo) {
  return apiRequest(
    `/operaciones/programacion/linea/${lineaId}/secuencia/`,
    { method: 'POST', body: cuerpo },
    { cookies }
  );
}

/**
 * Los planes semanales de la organizacion.
 *
 * Cierra la brecha que el propio backend describe: 'programar/' exige un
 * 'programacion_semanal_id' que hasta ahora no habia forma de averiguar por la
 * API, y la pantalla solo podia pedirle a una persona que escribiera un UUID.
 *
 * `soloConLineas` usa el filtro del backend, no uno propio: quien decide que
 * estado admite ordenes nuevas es
 * 'programacion.py::ESTADOS_DE_PLAN_QUE_ADMITEN_LINEAS', la MISMA constante
 * que aplica el servicio al programar. Filtrar aca por una lista copiada seria
 * un segundo criterio que se desincroniza del primero.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {boolean} [soloConLineas]
 */
export async function listarPlanes({ cookies }, soloConLineas = true) {
  const query = soloConLineas ? '?admite_lineas=1' : '';
  try {
    const d = await apiRequest(`/operaciones/programacion/${query}`, {}, { cookies });
    return { count: d?.count ?? 0, planes: d?.resultados ?? [], error: null };
  } catch (/** @type {any} */ err) {
    // El 404 merece su propio texto: significa que ESTE entorno todavia no
    // tiene la ruta, no que la empresa no tenga planes. Confundir las dos
    // cosas manda a buscar el problema al lado equivocado.
    if (err?.status === 404) {
      return {
        count: null,
        planes: [],
        error: {
          codigo: 'RUTA_AUSENTE',
          status: 404,
          mensaje:
            'El listado de planes semanales todavía no está disponible en este entorno. ' +
            'No es que no haya planes: la ruta no responde.'
        }
      };
    }
    return { count: null, planes: [], error: traducirError(err, 'los planes semanales') };
  }
}

/**
 * Programa una orden dentro de un plan.
 *
 * El 'programacion_semanal_id' sale del plan que la persona eligio de la lista
 * real; 'programada_para' de la fecha que escribio. Las reglas siguen siendo
 * del backend: que el plan admita lineas, que la fecha caiga en su semana y
 * que una adicion a un plan ya publicado exija causa las valida
 * 'programar_orden', no esta capa.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 * @param {{ programacion_semanal_id: string, programada_para: string, causa?: string, motivo?: string, zona?: string }} cuerpo
 */
export async function programarOrden({ cookies }, ordenId, cuerpo) {
  return apiRequest(
    `/campo/trabajos/${ordenId}/programar/`,
    { method: 'POST', body: cuerpo },
    { cookies }
  );
}

/**
 * Los planes en cuya semana cae `dia`.
 *
 * NO ES UNA REGLA NUEVA. 'programar_orden' exige que la linea caiga entre
 * 'semana_inicio' y 'semana_fin', y el serializer expone 'semana_fin'
 * justamente "para que la pantalla no ofrezca una opcion que el servicio va a
 * rechazar despues". Esto es leer esos dos campos, no inventar un criterio.
 *
 * @param {any[]} planes
 * @param {string} dia  YYYY-MM-DD
 */
export function planesQueCubren(planes, dia) {
  if (!dia) return planes;
  return planes.filter((p) => {
    if (!p?.semana_inicio || !p?.semana_fin) return true; // sin dato, no se descarta
    return p.semana_inicio <= dia && dia <= p.semana_fin;
  });
}

/**
 * Qué material tocó una orden.
 *
 * NO SE RECALCULA NADA ACA
 * ------------------------
 * El backend devuelve movimientos que ya existen, agrupados. Esta capa los pasa
 * tal cual. Sumar acá crearia una segunda contabilidad que compite con
 * `existencia(ubicacion, material)`, que es la unica verdad del libro.
 *
 * `custodia` viene APAGADO por defecto. El kit del dia es de la persona, no del
 * trabajo, y pedirlo siempre invitaria a dibujarlo como material de esta orden.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 * @param {{ custodia?: boolean }} [opciones]
 */
export async function leerMaterialesDeOrden({ cookies }, ordenId, opciones = {}) {
  const sufijo = opciones.custodia ? '?custodia=1' : '';
  try {
    const d = await apiRequest(
      `/campo/trabajos/${ordenId}/materiales/${sufijo}`,
      {},
      { cookies }
    );
    return { datos: d, error: null };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'los materiales de esta orden') };
  }
}

/**
 * La bitácora de la intervención: los cuatro momentos y los nueve eventos que ya
 * se escribían, en una sola línea de tiempo, más los formularios vigentes.
 *
 * LOS FORMULARIOS NO ESTÁN EN ESTE ARCHIVO, Y ES EL PUNTO
 * ------------------------------------------------------
 * Vienen del backend, que los deriva de `WorkTypeVersion`. Escribir acá los
 * campos de un ISP --un nivel 1550, un PLC-- obligaría a un commit del frontend
 * cada vez que una empresa nueva midiera otra cosa.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 */
export async function leerSeguimientoDeOrden({ cookies }, ordenId) {
  try {
    const d = await apiRequest(`/campo/trabajos/${ordenId}/seguimiento/`, {}, { cookies });
    return { datos: d, error: null };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'la bitácora de esta orden') };
  }
}

/**
 * Agrega un reporte a la bitácora.
 *
 * `idempotencyKey` viaja como cabecera porque es lo que hace que un reintento de
 * red no deje dos AVANCE idénticos: la bitácora contaría dos hechos donde hubo
 * uno. Un valor nuevo por intento sería un identificador único, no una clave
 * idempotente.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 * `requiereNoc` y `detener` viajan APARTE de las respuestas, y solo significan
 * algo en un bloqueo. Son datos de plataforma: el campo del formulario que dice
 * "qué necesitás del NOC" lo nombra cada empresa como quiere, y un filtro que
 * dependa de ese nombre deja de funcionar con la segunda.
 *
 * @param {{ momento: string, respuestas: Record<string, any>, requiereNoc?: boolean, detener?: boolean, idempotencyKey?: string }} reporte
 */
export async function registrarSeguimiento({ cookies }, ordenId, reporte) {
  const cabeceras = reporte.idempotencyKey
    ? { 'Idempotency-Key': reporte.idempotencyKey }
    : undefined;
  try {
    const d = await apiRequest(
      `/campo/trabajos/${ordenId}/seguimiento/`,
      {
        method: 'POST',
        // `apiRequest` serializa el objeto: pasarlo ya en texto lo enviaria
        // como un string JSON dentro de otro.
        body: {
          momento: reporte.momento,
          respuestas: reporte.respuestas,
          // Se mandan siempre que vengan definidos. Olvidarlos aca fue un defecto
          // real: el backend los respetaba --tenia prueba-- y esta capa los
          // dejaba caer, asi que la bandeja del NOC quedaba siempre vacia.
          ...(reporte.requiereNoc !== undefined
            ? { requiere_noc: !!reporte.requiereNoc }
            : {}),
          ...(reporte.detener !== undefined ? { detener: !!reporte.detener } : {})
        },
        ...(cabeceras ? { headers: cabeceras } : {})
      },
      { cookies }
    );
    return { datos: d, error: null };
  } catch (/** @type {any} */ err) {
    // 422 trae los errores POR CAMPO: se devuelven tal cual para que la pantalla
    // los pinte donde corresponde en vez de un solo texto arriba.
    // `api-helpers` cuelga el cuerpo del error en `.body` (y el status en `.status`).
    const campos = err?.body?.campos ?? null;

    // El 422 trae el motivo escrito para quien lo va a leer: "falta el nivel",
    // "no se puede cerrar lo que nunca se inició". `traducirError` no lo conoce
    // --es el traductor de las LECTURAS de esta pantalla-- y su texto genérico
    // ("no fue posible consultar…") tapa justamente el dato útil.
    if (err?.status === 422) {
      return {
        datos: null,
        error: {
          codigo: 'SEGUIMIENTO_INVALIDO',
          status: 422,
          mensaje:
            err?.body?.detalle ??
            'El reporte no se puede guardar todavía: revisá los campos marcados.',
          campos
        }
      };
    }

    const error = traducirError(err, 'el reporte de seguimiento');
    return { datos: null, error: { ...error, campos } };
  }
}

/**
 * Los bloqueos vivos de la empresa.
 *
 * DOS FILTROS, NO UNO
 * -------------------
 * `soloNoc` existe para que «Bloqueados» y «Requiere NOC» puedan ser dos filtros
 * distintos y los dos digan la verdad. Un trabajo detenido esperando al cliente
 * está bloqueado y NO requiere NOC; mezclarlos llenaría esa bandeja de cosas que
 * nadie de esa mesa puede resolver, y a la semana la dejarían de mirar.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {{ soloNoc?: boolean }} [opciones]
 */
export async function leerBloqueosAbiertos({ cookies }, opciones = {}) {
  const sufijo = opciones.soloNoc ? '?requiere_noc=1' : '';
  try {
    const d = await apiRequest(`/campo/bloqueos/${sufijo}`, {}, { cookies });
    return { datos: d, error: null };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'los bloqueos abiertos') };
  }
}

/**
 * Destraba un trabajo detenido.
 *
 * El estado al que vuelve lo guardó el bloqueo al abrirse; `volverA` solo se manda
 * cuando alguien quiere otro destino, y el backend lo valida contra la máquina de
 * transiciones igual que cualquier otro movimiento de estado.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} ordenId
 * @param {{ queSeHizo: string, rol?: string, volverA?: string, idempotencyKey?: string }} datos
 */
export async function resolverBloqueo({ cookies }, ordenId, datos) {
  const cabeceras = datos.idempotencyKey
    ? { 'Idempotency-Key': datos.idempotencyKey }
    : undefined;
  try {
    const d = await apiRequest(
      `/campo/trabajos/${ordenId}/bloqueo/resolver/`,
      {
        method: 'POST',
        body: {
          que_se_hizo: datos.queSeHizo,
          resuelto_por_rol: datos.rol ?? '',
          ...(datos.volverA ? { volver_a: datos.volverA } : {})
        },
        ...(cabeceras ? { headers: cabeceras } : {})
      },
      { cookies }
    );
    return { datos: d, error: null };
  } catch (/** @type {any} */ err) {
    // 422: el motivo está escrito para quien lo lee. 409: no hay bloqueo abierto,
    // que casi siempre significa que alguien lo resolvió mientras mirabas.
    if (err?.status === 422 || err?.status === 409) {
      return {
        datos: null,
        error: {
          codigo: err.status === 409 ? 'SIN_BLOQUEO_ABIERTO' : 'BLOQUEO_INVALIDO',
          status: err.status,
          mensaje:
            err?.body?.detalle ??
            (err.status === 409
              ? 'Este trabajo ya no tiene un bloqueo abierto: alguien lo resolvió.'
              : 'No se pudo resolver el bloqueo.'),
          campos: err?.body?.campos ?? null
        }
      };
    }
    return { datos: null, error: traducirError(err, 'este bloqueo') };
  }
}
