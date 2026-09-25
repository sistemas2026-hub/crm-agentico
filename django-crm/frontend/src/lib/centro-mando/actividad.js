/**
 * La cola de actividad: que se anima en la planta, y cuando.
 *
 * EL PROBLEMA QUE RESUELVE
 * Los datos llegan por sondeo cada 12 segundos (lib/centro-mando/eventos.js).
 * Si cada foto dispara de golpe todas sus animaciones, pasan dos cosas malas:
 * doce segundos de quietud absoluta seguidos de medio segundo en el que se
 * mueven ocho cosas a la vez --que nadie puede leer-- y la sensacion de que
 * la pantalla esta congelada el resto del tiempo.
 *
 * La cola reparte esos eventos a lo largo del intervalo. No inventa nada:
 * cada animacion corresponde a un evento que el motor conto de verdad. Lo
 * unico que se decide aqui es EN QUE MOMENTO se muestra, y ese reparto es
 * honesto porque la pantalla nunca afirma que algo este pasando "ahora": el
 * sello dice "leido hace N segundos" y esta ahi justamente para eso.
 *
 * LO QUE SI SERIA DESHONESTO, y por eso no se hace: generar movimiento sin
 * un evento detras. Si en una ventana no paso nada, la planta se queda
 * quieta. Que este quieta ES la informacion.
 */

/** Cuantos eventos se animan por lectura. Mas que esto no se alcanza a leer. */
export const MAXIMO_POR_LECTURA = 8;

/**
 * Los eventos de un panorama que NO estaban en el anterior.
 *
 * Se comparan por (instante + agente + herramienta) y no por identidad: el
 * payload se serializa de nuevo en cada sondeo, asi que los objetos nunca son
 * los mismos aunque describan el mismo hecho. Sin esta clave, cada lectura
 * reanimaria los veinte eventos del ticker y la planta seria una fiesta
 * permanente que no significa nada.
 *
 * @param {any[]} antes
 * @param {any[]} ahora
 */
export function eventosNuevos(antes, ahora) {
  const clave = (e) => `${e.en}|${e.agente}|${e.herramienta || e.motivo || e.tipo}`;
  const vistos = new Set((antes || []).map(clave));
  return (ahora || []).filter((e) => !vistos.has(clave(e)));
}

/**
 * Que animacion le toca a un evento, y cuanto dura.
 *
 * `null` significa que ese evento no se anima. Es deliberado que la mayoria
 * no lo haga: si todo se mueve, el movimiento deja de ser una senal.
 *
 * La firma acepta CUALQUIER cosa a proposito: esto se llama sobre los
 * eventos del payload, y un payload puede traer una forma que esta version
 * de la pantalla no conoce -- un tipo de evento nuevo, un campo que falta.
 * Fallar ahi dejaria la planta sin pintar por un evento raro.
 *
 * @param {any} evento
 */
export function animacionDe(evento) {
  switch (evento?.tipo) {
    // Lo que se va de la oficina: el caso deja el edificio y pasa a una
    // persona. Es el unico evento que MERECE verse salir.
    case 'escalada':
      return { forma: 'sale', duracion: 1800, prioridad: 0 };
    // Una accion con efecto fuera del sistema.
    case 'accion':
      return { forma: 'herramienta', duracion: 1100, prioridad: 1 };
    case 'herramienta_fallida':
      return { forma: 'falla', duracion: 1400, prioridad: 0 };
    case 'consulta':
      return { forma: 'herramienta', duracion: 900, prioridad: 2 };
    default:
      return null;
  }
}

/**
 * Reparte los eventos a lo largo de la ventana, en orden de prioridad.
 *
 * Los que mas dicen salen primero --una escalada antes que una consulta-- y
 * si hay mas de los que caben, se quedan fuera los menos importantes. Se
 * devuelve `descartados` para que la pantalla pueda decirlo en vez de fingir
 * que no paso nada mas.
 *
 * @param {any[]} eventos
 * @param {{ventanaMs?: number, maximo?: number, desde?: number}} opciones
 */
export function repartir(eventos, opciones = {}) {
  const { ventanaMs = 12000, maximo = MAXIMO_POR_LECTURA, desde = 0 } = opciones;

  const candidatos = (eventos || [])
    .map((e) => ({ evento: e, anim: animacionDe(e) }))
    .filter((x) => x.anim);

  const ordenados = [...candidatos].sort((a, b) => a.anim.prioridad - b.anim.prioridad);
  const elegidos = ordenados.slice(0, maximo);
  const descartados = ordenados.length - elegidos.length;

  /* El reparto deja un margen al final: la ultima animacion tiene que
     TERMINAR antes de la proxima lectura, o se cortaria a la mitad cuando el
     repintado la reemplace. */
  const masLarga = Math.max(0, ...elegidos.map((x) => x.anim.duracion));
  const util = Math.max(0, ventanaMs - masLarga - 400);
  const paso = elegidos.length > 1 ? util / (elegidos.length - 1) : 0;

  return {
    descartados,
    programadas: elegidos.map((x, i) => ({
      id: `${desde}-${i}`,
      evento: x.evento,
      forma: x.anim.forma,
      duracion: x.anim.duracion,
      retraso: Math.round(paso * i)
    }))
  };
}
