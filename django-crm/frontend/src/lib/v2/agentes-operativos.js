/**
 * LOS AGENTES OPERATIVOS: los que trabajan sobre la operación, no sobre una
 * conversación.
 *
 * POR QUÉ ESTA LISTA EXISTE APARTE
 * --------------------------------
 * `/agentes` lista lo que devuelve el motor, y el motor solo conoce sus roles
 * conversacionales (`config.roles`). El Supervisor NOC IA no es uno de ellos:
 * vive entero en el CRM (app `operaciones`), no habla con nadie, no tiene
 * prompt y no llama a ningún modelo de lenguaje — sus habilidades son código
 * determinista. Por eso no aparecía: la pantalla no tenía forma de verlo.
 *
 * Esta lista lo REPRESENTA, no lo registra. No lo convierte en un rol del
 * tenant: si lo declaráramos como rol, el motor lo metería en el enrutador de
 * derivación y alguien podría acabar derivándole un cliente.
 *
 * LO QUE NO LLEVA, Y ES A PROPÓSITO
 * ---------------------------------
 * Ni una métrica. Cuántas propuestas tiene pendientes, cuántas señales ve o
 * en qué estado está su interruptor son datos que cambian cada minuto y que
 * su propio tablero ya muestra con su fuente. Escribir aquí un número sería
 * inventar una segunda verdad que envejece sola: esta tarjeta dice QUÉ ES y
 * lleva a donde está el dato.
 */

/** @typedef {{clave: string, nombre: string, rotulo: string, descripcion: string, href: string, enlace: string}} AgenteOperativo */

/** @type {AgenteOperativo[]} */
export const AGENTES_OPERATIVOS = [
  {
    clave: 'supervisor-noc',
    nombre: 'Supervisor NOC IA',
    //  El rótulo dice las dos cosas que lo distinguen de los de al lado: que
    //  es operativo (no conversacional) y sobre qué trabaja.
    rotulo: 'Agente operativo · Supervisión técnica',
    //  02/11/2026: decia "no ejecuta ninguna accion: cada propuesta queda
    //  pendiente". Dejo de ser cierto en octubre -- hace solo las tareas que la
    //  empresa le delega -- y contradecia el objetivo del producto (PRD §1:
    //  reemplazar la mano de obra; una persona solo en lo critico).
    descripcion:
      'Revisa la operación técnica —casos, órdenes, programación y plazos—, propone qué ' +
      'hacer y hace solo las tareas que la empresa le delega: pasar casos a Despacho, armar ' +
      'la jornada, crear y publicar órdenes, cerrar lo que revisó. No conversa con nadie, y ' +
      'lo crítico sigue esperando a una persona.',
    href: '/supervisor-noc',
    enlace: 'Abrir su tablero'
  }
];
