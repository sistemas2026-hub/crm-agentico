/**
 * Las acciones propuestas que quedaron pendientes sin conversación (G3).
 *
 * QUÉ SON
 * -------
 * Escrituras reales contra sistemas externos —crear un ticket, registrar una
 * promesa de pago— que se propusieron antes de que las acciones se vincularan
 * a una conversación, y que nadie aprobó ni rechazó nunca. Medidas en
 * producción: 36 (A5).
 *
 * POR QUÉ NO SE PUEDEN APROBAR
 * ----------------------------
 * Sin conversación no hay contexto actual contra el cual comprobar que lo que
 * se iba a hacer todavía tiene sentido. Aprobarla ejecutaría los argumentos
 * congelados de hace semanas: un ticket por un problema que quizá ya se
 * resolvió, una promesa de pago con la fecha límite vencida. El contrato lo
 * prohíbe (X24) y el motor lo rechaza con 409.
 *
 * Por eso esta pantalla no tiene botón de aprobar. No está deshabilitado: no
 * existe. Un botón gris invita a preguntar cómo habilitarlo.
 *
 * LO QUE SÍ SE PUEDE HACER
 * ------------------------
 * Cancelar, con un motivo. Si el problema sigue vivo, la conversación de hoy
 * lo vuelve a proponer con su contexto y pasa por la revalidación normal —que
 * es lo que el contrato pide (§11.4), y es más seguro que revivir una
 * intención vieja.
 */

/** Qué hace cada herramienta, en palabras de quien va a revisar. */
const QUE_HACE = {
  crear_ticket: 'Crearía un ticket en el sistema del ISP',
  cerrar_ticket: 'Cerraría un ticket en el sistema del ISP',
  registrar_pago: 'Registraría un pago sobre una factura',
  promise_payment: 'Registraría una promesa de pago',
  promesa_pago: 'Registraría una promesa de pago',
  crear_cliente: 'Daría de alta un cliente'
};

/**
 * Por qué cancelar es la opción correcta para este tipo, en una línea.
 *
 * No es decoración: quien revisa 36 filas necesita saber qué cambia entre una
 * y otra sin abrir cada una. Y las dos razones son distintas de verdad.
 */
const POR_QUE_NO = {
  crear_ticket:
    'Un ticket creado hoy por un problema de hace semanas no se puede deshacer, y no hay forma de saber si ya existe uno igual.',
  promise_payment: 'La fecha límite de la promesa ya venció.',
  promesa_pago: 'La fecha límite de la promesa ya venció.'
};

export function queHace(accion) {
  return QUE_HACE[accion?.herramienta] ?? `Ejecutaría «${accion?.herramienta ?? '—'}»`;
}

export function porQueNoSeAprueba(accion) {
  return (
    POR_QUE_NO[accion?.herramienta] ??
    'Se propuso sin conversación, así que no hay contexto actual contra el cual revalidarla.'
  );
}

/**
 * Cuánto hace que espera, en palabras.
 *
 * La antigüedad se muestra porque ayuda a decidir —una intención de hace un
 * mes casi seguro ya no aplica—, pero NO es lo que la hace inejecutable: eso
 * es la falta de conversación, y vale igual para una de hace un minuto. Si
 * esta línea se leyera como el motivo, la regla parecería un plazo que alguien
 * podría estirar.
 */
export function antiguedad(accion, ahora = new Date()) {
  const creado = accion?.creado_en ? new Date(accion.creado_en) : null;
  if (!creado || Number.isNaN(creado.getTime())) return '';
  const dias = Math.floor((ahora - creado) / 86400000);
  if (dias < 1) return 'hoy';
  if (dias === 1) return 'hace 1 día';
  if (dias < 31) return `hace ${dias} días`;
  const meses = Math.floor(dias / 30);
  return meses === 1 ? 'hace 1 mes' : `hace ${meses} meses`;
}

/** Una fila lista para dibujar: sólo lo que hace falta para decidir. */
export function lineaDeAccion(accion, ahora = new Date()) {
  return {
    id: accion?.id,
    herramienta: accion?.herramienta ?? '',
    queHace: queHace(accion),
    resumen: accion?.resumen ?? '',
    antiguedad: antiguedad(accion, ahora),
    porQueNo: porQueNoSeAprueba(accion),
    esLegado: accion?.es_legado === true,
    // Sólo se puede cancelar lo que sigue pendiente. Una ya resuelta se
    // muestra igual —el registro es el punto— pero sin acción.
    puedeCancelarse: accion?.estado === 'pendiente'
  };
}

/**
 * Cuántas hay de cada tipo, para el encabezado.
 *
 * Que «34 crearían tickets» esté arriba del todo cambia cómo se lee la lista:
 * no son 36 filas iguales, son 34 visitas técnicas y 2 promesas vencidas.
 */
export function resumenPorTipo(acciones = []) {
  const cuenta = new Map();
  for (const a of acciones) {
    const clave = a?.herramienta ?? '—';
    cuenta.set(clave, (cuenta.get(clave) ?? 0) + 1);
  }
  return [...cuenta.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([herramienta, cuantas]) => ({
      herramienta,
      cuantas,
      queHace: queHace({ herramienta })
    }));
}
