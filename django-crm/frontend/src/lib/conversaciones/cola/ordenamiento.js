/**
 * Por dónde empezar: el orden de la cola de conversaciones.
 *
 * POR QUÉ ESTO ES UN MÓDULO
 * -------------------------
 * Porque de esto depende D18 —que una escalada nueva sin dueño no quede
 * enterrada detrás de decenas de conversaciones viejas— y hasta acá no había
 * NINGUNA prueba que lo protegiera. La Fase 0B desarma la cola en componentes,
 * y el orden es lo único de esa pantalla que puede romperse sin que se note
 * mirándola: una lista mal ordenada se ve perfecta.
 *
 * El harness de vitest corre en `node` y no compila `.svelte`, así que para
 * tener guarda hay que poder importar estas funciones. `+layout.svelte` usa
 * ESTAS MISMAS, no una copia: un test contra una reimplementación paralela
 * probaría el test, no la cola.
 *
 * Extracción mecánica: mismos cuerpos, mismos comentarios, mismos valores. El
 * único cambio es que `ordenar` recibe `orden` como parámetro en vez de leerlo
 * del estado del componente.
 */
import { pendiente } from '$lib/conversaciones/estado.js';

// Con decenas esperando, "la mas nueva primero" ordena al reves de lo que
// hace falta: quien escalo hace tres dias y no volvio a escribir se hunde
// al fondo, y es justo el que lleva tres dias esperando.
//
// El orden es: primero las que esperan a alguien, y entre ellas la de
// espera mas larga arriba. El resto queda como estaba, por ultima
// actividad. No hay un puntaje ponderado a proposito -- un numero que
// mezcla antiguedad, insistencia y motivo no se puede explicar, y quien
// atiende tiene que poder entender por que una fila esta donde esta.
export const espera = (/** @type {any} */ c) =>
  new Date(c.escalada_en ?? c.actualizado_en).getTime();

export const HORA = 3600 * 1000;

/** Horas que lleva esperando. 0 si no espera a nadie. */
export const horasEsperando = (/** @type {any} */ c) =>
  pendiente(c) ? Math.max(0, (Date.now() - espera(c)) / HORA) : 0;

// Los motivos donde hay una persona molesta del otro lado pesan mas que un
// tramite. No es un puntaje afinado -- es un desempate, y por eso son dos
// valores y no cinco: cualquier cosa mas fina seria inventada.
export const MOTIVO_URGENTE = new Set(['frustracion_detectada', 'tres_fallos_seguidos']);

/* B3.5 (D18): "Recomendado" ya NO se calcula aca. El motor manda la
   proyeccion de cada conversacion (nucleo/relevo/proyeccion.py): en que
   banda cae, desde cuando espera y por que, todo derivado de la verdad
   durable. Esta pantalla solo ordena por (banda, esperando_desde) y muestra
   el motivo en palabras.

   El puntaje que vivia aca ordenaba por antiguedad, y por eso una escalada
   nueva sin dueno entraba detras de decenas de conversaciones viejas: es
   D18. Se conserva 'peso' solo como respaldo para una respuesta del motor
   sin proyeccion (un motor viejo durante un despliegue). */
export const bandaDe = (/** @type {any} */ c) => (typeof c.banda === 'number' ? c.banda : 99);
export const esperaDesde = (/** @type {any} */ c) =>
  c.esperando_desde ? new Date(c.esperando_desde).getTime() : null;

/** El orden de la cola, igual que proyeccion.orden_de_cola en el motor. */
export function porBanda(/** @type {any} */ a, /** @type {any} */ b) {
  if (bandaDe(a) !== bandaDe(b)) return bandaDe(a) - bandaDe(b);
  const ea = esperaDesde(a);
  const eb = esperaDesde(b);
  if (ea === null && eb === null) return 0;
  if (ea === null) return 1;          // sin fecha: al final de su banda
  if (eb === null) return -1;
  return ea - eb;                     // el que mas espera, primero
}

/** Respaldo si el motor no manda proyeccion. Ver el comentario de arriba. */
export function peso(/** @type {any} */ c) {
  if (!pendiente(c)) return -1;
  // La espera es la base y manda: es lo que de verdad mide el maltrato al
  // cliente. Se cuenta en dias para que las otras dos señales puedan
  // moverla sin taparla del todo.
  let p = horasEsperando(c) / 24;
  // Volver a escribir mientras espera es alguien golpeando la puerta, y
  // tiene que ganarle a la antiguedad: quien escribio hace dos minutos esta
  // ahi AHORA, y quien lleva 26 dias ya se acostumbro a esperar.
  //
  // 30 dias equivalentes, no 3: con el peso anterior una insistencia de hoy
  // perdia contra cualquier caso de mas de tres dias, y hay 34 con mas de
  // una semana. En la practica no subia a nadie.
  //
  // Ojo con lo que esto NO arregla: hay CERO mensajes posteriores a una
  // escalada en toda la base, y no porque nadie insista -- las
  // conversaciones se cierran a las 24 h de inactividad, asi que quien
  // vuelve a los dos dias abre una conversacion NUEVA y su insistencia no
  // se cuenta como tal. Esta señal solo ve al que insiste dentro del dia.
  if (c.mensajes_tras_escalar > 0) p += 30 + Math.min(c.mensajes_tras_escalar, 10);
  if (MOTIVO_URGENTE.has(c.motivo_escalamiento)) p += 2;
  return p;
}

/** La hora del ULTIMO MENSAJE, de quien sea -- cliente, asistente o
    colaborador. No 'actualizado_en': esa la mueve cualquier cosa que toque
    la fila, incluido cerrarla, y una conversacion cerrada hoy con su ultimo
    mensaje de hace 26 dias quedaba arriba de una con charla de verdad ayer. */
export const actividad = (/** @type {any} */ c) =>
  new Date(c.ultimo_mensaje_en ?? c.actualizado_en).getTime();

/**
 * @param {any[]} lista
 * @param {string} orden  uno de ORDENES: actividad | recomendado | espera | creacion
 */
export function ordenar(lista, orden) {
  const recientes = (/** @type {any} */ a, /** @type {any} */ b) =>
    new Date(b.actualizado_en).getTime() - new Date(a.actualizado_en).getTime();

  // Actividad: SIN bloque de prioridad delante. Es lo que hace que un
  // mensaje que acaba de entrar aparezca primero aunque el bot lo este
  // llevando solo -- que es justo para lo que sirve esta vista.
  if (orden === 'actividad') {
    return [...lista].sort((a, b) => actividad(b) - actividad(a));
  }
  if (orden === 'creacion') return [...lista].sort(recientes);

  return [...lista].sort((a, b) => {
    // En los dos ordenes que priorizan, lo que espera va primero: una
    // conversacion resuelta no compite por el lugar de arriba.
    const pa = pendiente(a) ? 0 : 1;
    const pb = pendiente(b) ? 0 : 1;
    if (pa !== pb) return pa - pb;
    if (pa === 1) return recientes(a, b);
    // 'Mayor espera' es a proposito el orden CRUDO, sin ponderar: existe
    // para poder comprobar el otro. Si "Recomendado" pone algo arriba que
    // no lleva la espera mas larga, se puede ver por que cambiando aca.
    if (orden === 'espera') return espera(a) - espera(b);
    if (typeof a.banda === 'number' || typeof b.banda === 'number') return porBanda(a, b);
    return peso(b) - peso(a);
  });
}
