/**
 * La lectura óptica de SmartOLT, traducida a lo que la pantalla dibuja.
 *
 * POR QUE EXISTE ESTE ARCHIVO
 * ---------------------------
 * Vivía dentro de `NetworkPanel.svelte` y ahí no se podía probar. El
 * 22/09/2026 se vio en PRODUCCION el resultado: el distintivo del estado de la
 * ONU decía literalmente «TRUE» y la potencia óptica no aparecía nunca. Las
 * dos cosas eran el mismo error, y ninguna prueba podía verlo porque no había
 * ninguna función que probar.
 *
 * EL SOBRE DE SMARTOLT, QUE ES DE DONDE SALIA EL «TRUE»
 * -----------------------------------------------------
 * Cada respuesta viene envuelta así:
 *
 *   {"response_code": "success", "status": true, "onu_status": "Online", ...}
 *
 * Ese `status` es del SOBRE -- significa "la llamada salió bien"-- y no tiene
 * NADA que ver con el estado de la ONU, que vive en `onu_status`. El motor
 * entrega estas dos lecturas crudas (`consultar_estado_ont` y
 * `consultar_senal_ont` no declaran `extraer_de`), así que el sobre llega
 * entero hasta acá. Leer `status` daba `true`, y `true` se dibujaba tal cual.
 *
 * Por eso `status` está EXPLICITAMENTE excluido más abajo en vez de
 * simplemente no buscarlo: el próximo que agregue un campo por tanteo se va a
 * topar con el comentario antes que con el bug.
 *
 * CUAL DE LAS DOS LONGITUDES DE ONDA
 * ----------------------------------
 * `onu_signal_1490` es la de BAJADA (OLT->ONU): la que la ONT recibe, y la
 * única sobre la que tiene sentido un umbral de "señal débil". `1310` es la de
 * subida y mide otra cosa. No es una preferencia: el propio tenant declara sus
 * `veredictos` sobre `onu_signal_1490`.
 *
 * TOLERA LAS DOS FORMAS, A PROPOSITO
 * ----------------------------------
 * Hoy llega el sobre crudo. Si alguien agrega `extraer_de: onu_signal` a la
 * herramienta -- que sería una mejora-- el dato llegaría desenvuelto y con los
 * nombres cortos. Se aceptan las dos formas para que ese cambio no vuelva a
 * romper la pantalla en silencio.
 */

/** El primer valor presente de una lista de claves. Nunca devuelve ''. */
function primero(objeto, claves) {
  if (!objeto || typeof objeto !== 'object') return null;
  for (const k of claves) {
    const v = objeto[k];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  return null;
}

/**
 * Desenvuelve el sobre si está, o devuelve el objeto tal cual.
 * @param {any} crudo
 * @param {string[]} claves nombres posibles del sobre (p.ej. 'onu_status')
 */
function desenvolver(crudo, claves) {
  if (!crudo || typeof crudo !== 'object') return null;
  for (const k of claves) {
    const dentro = crudo[k];
    // Sólo si es un OBJETO: 'onu_status' a veces es el texto del estado
    // ("Online") y no un contenedor. En ese caso el dato ya está en la raíz.
    if (dentro && typeof dentro === 'object' && !Array.isArray(dentro)) return dentro;
  }
  return crudo;
}

/** Un número, o null. '-' y '' no son números: SmartOLT los usa para "no reporta". */
export function numeroODinero(v) {
  if (v === null || v === undefined || v === '' || v === '-') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * La medición lista para dibujar, o null si no hay nada que mostrar.
 * @param {any} lectura  el payload de /conversaciones/<id>/optica
 */
export function medicionDe(lectura) {
  const o = lectura?.optica;
  if (!o) return null;

  const est = desenvolver(o.estado, ['onu_status', 'onu', 'estado']);
  const sen = desenvolver(o.senal, ['onu_signal', 'signal', 'senal']);

  /* El estado de la ONU. NUNCA 'status': ese es el del sobre y vale `true`.
     Si 'onu_status' vino como texto en la raíz, se lee de ahí. */
  let enlace = primero(est, ['onu_status', 'status_onu', 'estado_onu']);
  if (enlace === null && typeof o.estado?.onu_status === 'string') {
    enlace = o.estado.onu_status;
  }
  // Un booleano no es un estado. Si aun así llegara uno, no se dibuja.
  if (typeof enlace === 'boolean') enlace = null;

  const rx = numeroODinero(
    primero(sen, ['onu_signal_1490', 'signal_1490']) ??
    primero(o.senal, ['onu_signal_1490', 'signal_1490'])
  );

  /* La clasificación en texto que ya hace SmartOLT ("Very good"). Es útil
     junto al número: el operador que no lee dBm igual entiende. Sólo se toma
     si es TEXTO -- 'onu_signal' es el nombre del sobre y también el de este
     campo, así que puede venir cualquiera de los dos. */
  const clasificacionCruda = primero(o.senal, ['onu_signal']) ?? primero(sen, ['onu_signal', 'signal']);
  const clasificacion = typeof clasificacionCruda === 'string' ? clasificacionCruda : null;

  const medicion = {
    serial: o.serial ?? null,
    enlace: typeof enlace === 'string' ? enlace : null,
    clasificacion,
    rx,
    /* La de SUBIDA. Se guarda aparte y no se mezcla con `rx`: son dos
       medidas distintas y confundirlas es justo el error que este archivo
       documenta. */
    rxSubida: numeroODinero(primero(sen, ['onu_signal_1310', 'signal_1310'])),
    desde: primero(est, ['last_status_change']) ?? primero(o.estado, ['last_status_change']),
    // Estos dos sólo existen en 'get_onu_full_status_info', que esta pantalla
    // no llama (tarda ~10s y el proveedor pide no usarlo en bucle). Se buscan
    // igual por si algún tenant declara esa herramienta.
    encendido: primero(est, ['uptime', 'ONT online duration']),
    causaCaida: primero(est, ['last_down_cause_interpretado', 'last_down_cause', 'Last down cause'])
  };

  // Si no se pudo leer NI el estado NI la potencia, no hay medición que
  // mostrar: dibujar una tarjeta vacía se lee como "el sistema está roto".
  if (medicion.enlace === null && medicion.rx === null) return null;
  return medicion;
}

/**
 * ¿El enlace está caído? null = no se puede afirmar.
 * Se compara en minúsculas porque SmartOLT devuelve 'Online'/'Offline'.
 */
export function enlaceCaido(medicion) {
  if (!medicion?.enlace) return null;
  return String(medicion.enlace).toLowerCase() !== 'online';
}

/**
 * ¿La potencia está por debajo del umbral de la empresa?
 * null = no se puede afirmar (sin umbral, o sin lectura). "No sabemos" no es
 * "está bien", y por eso son tres estados y no dos.
 */
export function potenciaAtenuada(medicion, umbral) {
  if (umbral === null || umbral === undefined) return null;
  if (medicion?.rx === null || medicion?.rx === undefined) return null;
  const u = Number(umbral);
  if (!Number.isFinite(u)) return null;
  // Son negativos: más negativo es peor, así que atenuado es MENOR.
  return medicion.rx < u;
}
