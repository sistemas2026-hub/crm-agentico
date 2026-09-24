/**
 * La maquina de estados de un agente del centro de mando.
 *
 * Vive aparte de los componentes a proposito: que un estado exista, con que
 * color se pinta y a cual puede pasar es una regla del dominio, no una
 * decision de presentacion. Asi se puede probar sin montar la pantalla, que
 * es justo lo que hace falta -- un estado mal derivado no se ve: muestra
 * tranquilo a un agente que esta con errores.
 *
 * LOS COLORES SON LOS DEL TEMA CLARO
 * El tablero se pinta sobre blanco, como el resto del CRM. Los tonos neon
 * del primer diseno (#06B6D4, #22C55E) sobre blanco quedaban por debajo del
 * minimo legible -- medido el 24/09/2026: la tarea del agente daba 3.68 de
 * contraste y la leyenda 2.56, contra el 4.5 que pide WCAG AA. Estos tonos
 * dicen lo mismo y se leen: ninguno baja de 4.7 sobre blanco.
 *
 * OCHO ESTADOS, SEIS QUE EL MOTOR EMITE HOY
 * La interfaz sabe pintar los ocho. El motor (nucleo/canales/api.py) solo
 * emite los que puede medir; `waiting_tool` y `completed` estan definidos
 * aqui para que la Fase 2 no tenga que tocar la maquina cuando exista el
 * dato, pero hoy no llegan. El motivo esta escrito en la derivacion del
 * motor: `tool_calls` se escribe al TERMINAR la llamada (no hay fila en
 * vuelo) y `completed` es estado de una tarea, no de un agente.
 */

/** @typedef {'idle'|'working'|'waiting_tool'|'waiting_user'|'waiting_approval'|'completed'|'error'|'offline'} EstadoAgente */

/**
 * @type {Record<EstadoAgente, {
 *   rotulo: string, color: string, pulso: boolean, orden: number,
 *   emitido: boolean, descripcion: string
 * }>}
 */
export const ESTADOS = {
  error: {
    rotulo: 'CON ERRORES',
    color: '#B91C1C',
    pulso: true,
    orden: 0,
    emitido: true,
    descripcion: 'Alguna de sus herramientas falló en la ventana reciente.'
  },
  waiting_approval: {
    rotulo: 'ESPERA APROBACIÓN',
    color: '#6D28D9',
    pulso: true,
    orden: 1,
    emitido: true,
    descripcion: 'Ejecutó una acción cuyo efecto todavía nadie comprobó.'
  },
  working: {
    rotulo: 'TRABAJANDO',
    color: '#0E7490',
    pulso: true,
    orden: 2,
    emitido: true,
    descripcion: 'Está ejecutando herramientas o atendiendo conversaciones.'
  },
  waiting_tool: {
    rotulo: 'ESPERA HERRAMIENTA',
    color: '#0369A1',
    pulso: true,
    orden: 3,
    emitido: false,
    descripcion: 'Llamó a un sistema externo y aún no le responde.'
  },
  waiting_user: {
    rotulo: 'ESPERA RESPUESTA',
    color: '#A15C07',
    pulso: false,
    orden: 4,
    emitido: true,
    descripcion: 'Contestó y espera al cliente, o el caso pasó a una persona.'
  },
  completed: {
    rotulo: 'COMPLETADO',
    color: '#15803D',
    pulso: false,
    orden: 5,
    emitido: false,
    descripcion: 'Terminó la tarea que traía entre manos.'
  },
  idle: {
    rotulo: 'DISPONIBLE',
    color: '#15803D',
    pulso: false,
    orden: 6,
    emitido: true,
    descripcion: 'Sin conversaciones en curso.'
  },
  offline: {
    rotulo: 'FUERA DE LÍNEA',
    color: '#64748B',
    pulso: false,
    orden: 7,
    // No se emite: nada en la base dice que un agente esté apagado. Derivarlo
    // de "no tiene filas" es falso -- un agente que hoy no atendió a nadie
    // tampoco las tiene, y está vivo. Queda listo para cuando exista una
    // bandera de agente deshabilitado.
    emitido: false,
    descripcion: 'Deshabilitado: no atiende aunque esté configurado.'
  }
};

/** Los estados que el motor produce hoy. El resto espera a tener con qué medirse. */
export const EMITIDOS = /** @type {EstadoAgente[]} */ (
  Object.keys(ESTADOS).filter((e) => ESTADOS[/** @type {EstadoAgente} */ (e)].emitido)
);

/**
 * Transiciones que tienen sentido. No se usa para bloquear -- el motor es la
 * autoridad y si dice algo, se muestra -- sino para que la Fase 2 sepa qué
 * animación corresponde a cada paso, y para detectar en pruebas un salto que
 * no deberia ocurrir.
 *
 * @type {Record<EstadoAgente, EstadoAgente[]>}
 */
export const TRANSICIONES = {
  idle: ['working', 'offline'],
  working: ['waiting_tool', 'waiting_user', 'waiting_approval', 'completed', 'error', 'idle'],
  waiting_tool: ['working', 'error', 'completed'],
  waiting_user: ['working', 'idle', 'completed'],
  waiting_approval: ['working', 'completed', 'error'],
  completed: ['idle', 'working'],
  error: ['working', 'idle'],
  offline: ['idle', 'working']
};

const POR_DEFECTO = 'idle';

/** Normaliza lo que llegue del motor a un estado conocido. */
export function normalizar(estado) {
  return estado && estado in ESTADOS ? /** @type {EstadoAgente} */ (estado) : POR_DEFECTO;
}

export const rotuloDe = (estado) => ESTADOS[normalizar(estado)].rotulo;
export const colorDe = (estado) => ESTADOS[normalizar(estado)].color;
export const pulsaEn = (estado) => ESTADOS[normalizar(estado)].pulso;

/** ¿El paso de un estado a otro es uno de los previstos? */
export function transicionValida(desde, hacia) {
  const a = normalizar(desde), b = normalizar(hacia);
  return a === b || TRANSICIONES[a].includes(b);
}

/**
 * Orden de lectura: primero lo que exige atención, al final lo que está
 * quieto; dentro del mismo estado, el que más carga lleva.
 */
export function ordenar(agentes) {
  return [...agentes].sort(
    (a, b) =>
      ESTADOS[normalizar(a.estado)].orden - ESTADOS[normalizar(b.estado)].orden ||
      (b.conversaciones || 0) - (a.conversaciones || 0) ||
      String(a.nombre).localeCompare(String(b.nombre))
  );
}

/** Cuántos agentes hay en cada estado. Insumo del panel de métricas. */
export function repartoPorEstado(agentes) {
  /** @type {Record<string, number>} */
  const cuenta = {};
  for (const a of agentes) {
    const e = normalizar(a.estado);
    cuenta[e] = (cuenta[e] || 0) + 1;
  }
  return cuenta;
}
