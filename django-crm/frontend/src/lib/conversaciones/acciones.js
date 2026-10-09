/**
 * Las acciones que la IA propuso en esta conversación, y cómo terminaron (B5).
 *
 * LO QUE ESTE MÓDULO EXISTE PARA NO DEJAR PASAR
 * ---------------------------------------------
 * Antes de B5 una acción terminaba en «aprobada» y nada más — que es lo que
 * alguien decidió, no lo que pasó. El efecto podía haber fallado y la pantalla
 * decía lo mismo. Ahora hay cuatro finales distintos y cada uno pide algo
 * distinto de quien lo lee:
 *
 *   ejecutada_ok      se hizo. No hay nada que hacer.
 *   ejecutada_fallo   NO se hizo, y se sabe. Se puede volver a proponer.
 *   vencida           ya no aplicaba cuando se fue a aprobar. Tampoco se hizo.
 *   desconocida       NO SE SABE si se hizo. Y no se reintenta: reintentar un
 *                     ticket que quizá ya existe manda dos visitas técnicas al
 *                     mismo cliente. Espera a que alguien lo compruebe.
 *
 * `desconocida` es la que no puede leerse como «falló». Si la pantalla dice
 * que falló, alguien lo va a rehacer — que es exactamente lo que no debe
 * pasar. Es la misma distinción que sostiene el panel de sincronización (B4).
 */

const ESTADOS = {
  pendiente: {
    tono: 'neutro',
    titulo: 'Esperando aprobación',
    detalle: 'Todavía no se hizo nada.'
  },
  ejecutando: {
    tono: 'neutro',
    titulo: 'Ejecutándose',
    detalle: 'Alguien la aprobó y está corriendo ahora mismo.'
  },
  ejecutada_ok: {
    tono: 'ok',
    titulo: 'Hecha',
    detalle: 'Se ejecutó y el sistema externo la aceptó.'
  },
  ejecutada_fallo: {
    tono: 'error',
    titulo: 'No se pudo hacer',
    detalle: 'Se intentó y el sistema externo la rechazó. No quedó hecha.'
  },
  vencida: {
    tono: 'aviso',
    titulo: 'Ya no aplicaba',
    detalle: 'Cuando se fue a aprobar, la situación había cambiado. No se hizo nada.'
  },
  desconocida: {
    tono: 'aviso',
    titulo: 'No sabemos si llegó a hacerse',
    detalle:
      'El pedido pudo haber llegado al sistema externo. No se reintenta: hay que comprobarlo a mano antes de volver a pedirlo.'
  },
  rechazada: {
    tono: 'neutro',
    titulo: 'Rechazada',
    detalle: 'Alguien la evaluó y decidió que no.'
  },
  cancelada: {
    tono: 'neutro',
    titulo: 'Cancelada',
    detalle: 'Quedó obsoleta y no se va a ejecutar.'
  },
  aprobada: {
    // Legado: filas de antes de B5, cuando «aprobada» era el único final.
    tono: 'neutro',
    titulo: 'Aprobada (antes de B5)',
    detalle: 'De cuando el registro no distinguía si el efecto había ocurrido.'
  }
};

const SIN_ESTADO = {
  tono: 'aviso',
  titulo: 'Estado desconocido',
  detalle: 'No se pudo interpretar el estado de esta acción.'
};

export function estadoDeAccion(accion) {
  return ESTADOS[accion?.estado] ?? SIN_ESTADO;
}

/** Sólo una acción `pendiente` y todavía en plazo se puede aprobar. */
export function sePuedeAprobar(accion) {
  return accion?.estado === 'pendiente' && accion?.expirada !== true;
}

/**
 * Las que necesitan que una persona haga algo.
 *
 * `desconocida` entra aunque sea terminal: nadie la va a resolver sola, y
 * dejarla fuera la volvería invisible — que es el estado en el que estaban
 * las 36 del legado.
 */
export function esperanRevision(acciones = []) {
  return acciones.filter(
    (a) => a?.estado === 'desconocida' || a?.estado === 'ejecutando'
  );
}

export function lineaDeAccion(accion) {
  const estado = estadoDeAccion(accion);
  return {
    id: accion?.id,
    resumen: accion?.resumen ?? '',
    herramienta: accion?.herramienta ?? '',
    tono: estado.tono,
    titulo: estado.titulo,
    detalle: estado.detalle,
    puedeAprobarse: sePuedeAprobar(accion),
    // El plazo sólo se anuncia mientras todavía importa: decir «vence en 3
    // min» de algo que ya se ejecutó es ruido.
    venceEn: accion?.estado === 'pendiente' ? (accion?.vence_en ?? null) : null,
    expirada: accion?.expirada === true
  };
}

/** Lo que se muestra del hilo: las acciones, más recientes primero. */
export function lineasDeAcciones(acciones = []) {
  return acciones.map(lineaDeAccion);
}
