/**
 * QUÉ HACE EL SUPERVISOR SOLO, A LA VISTA  --  01/11/2026
 *
 * Hasta hoy esto vivía dentro del modal de «Alcance»: para saber qué tareas
 * estaban delegadas y si de verdad corrían había que abrirlo. Desde que el
 * Supervisor aprueba y cierra órdenes solo (30-31/10), es lo primero que
 * necesita saber quien mira la pantalla, al lado de lo que tiene que decidir.
 *
 * Lee la MISMA respuesta que el modal (`GET /api/supervisor-noc/autonomia`) y
 * aplica la MISMA regla de tres estados que él: no delegada, delegada y
 * funcionando, delegada pero sin actuar. Lo único que agrega es el freno de
 * mano: con el interruptor detenido ninguna actúa, y decir "Encendida" ahí
 * sería la mentira que el modal ya evitaba con su punto rojo.
 */

/**
 * @param {any} alcance  la respuesta de /api/supervisor-noc/autonomia, o null
 */
export function loQueHaceSolo(alcance) {
  if (!alcance) {
    return { leido: false, frenado: null, activas: [], sinDelegar: 0, actuan: 0, sinCatalogo: false };
  }
  const frenado = alcance.interruptor_permite === false;
  const catalogo = Array.isArray(alcance.delegaciones) ? alcance.delegaciones : null;
  if (!catalogo) {
    return { leido: true, frenado, activas: [], sinDelegar: 0, actuan: 0, sinCatalogo: true };
  }

  const activas = catalogo
    .filter((d) => d?.delegada)
    .map((d) => {
      /** @type {string | null} */
      let porQue = null;
      if (frenado) porQue = 'El freno de mano está puesto.';
      else if (!d.nivel_alcanza)
        porQue = `Necesita nivel ${d.exige_nivel} y el que aplica hoy es ${alcance.efectivo}.`;
      else if (d.la_despierta_algo && !d.la_despierta_algo.si)
        porQue = d.la_despierta_algo.por_que ?? 'Nada la está corriendo.';
      return {
        clave: d.clave,
        nombre: d.nombre,
        queHace: d.que_hace,
        delegadaEn: d.delegada_en ?? null,
        actua: porQue === null,
        porQue
      };
    });

  return {
    leido: true,
    frenado,
    activas,
    sinDelegar: catalogo.length - activas.length,
    actuan: activas.filter((t) => t.actua).length,
    sinCatalogo: false
  };
}

/**
 * LAS CLAVES DE LAS DOS TAREAS QUE VAN EN TARJETA PROPIA  --  01/11/2026
 *
 * Son las del catálogo del backend (operaciones/tareas_delegadas.py:
 * CERRAR_DESINCRONIZADOS y CERRAR_LO_REVISADO). Una prueba las fija: si alguien
 * las renombra allá, la tarjeta queda sin dato en vez de mostrar otra tarea.
 */
export const CLAVE_DESINCRONIZADOS = 'cerrar_desincronizados_con_diagnostico';
export const CLAVE_ORDENES = 'aprobar_y_cerrar_lo_que_dio_por_bueno';

/**
 * Las tarjetas de «Qué hace el Supervisor solo»: las dos tareas que más pesan,
 * en tarjeta propia, y las demás delegadas aparte. Cada tarjeta tiene TRES
 * estados y no dos -- apagada (no delegada), encendida (delegada y corriendo)
 * y no_actua (delegada pero algo la frena) --, con la regla de `loQueHaceSolo`.
 *
 * @param {any} alcance  la respuesta de /api/supervisor-noc/autonomia, o null
 */
export function tarjetasDeSolo(alcance) {
  if (!alcance) return { desincronizados: null, ordenes: null, otras: [], frenado: null };
  const solo = loQueHaceSolo(alcance);
  const catalogo = Array.isArray(alcance.delegaciones) ? alcance.delegaciones : [];
  /** @param {string} clave */
  const tarjeta = (clave) => {
    const d = catalogo.find((x) => x?.clave === clave);
    if (!d) return null;
    const activa = solo.activas.find((t) => t.clave === clave);
    return {
      clave,
      nombre: d.nombre,
      queHace: d.que_hace,
      estado: !activa ? 'apagada' : activa.actua ? 'encendida' : 'no_actua',
      porQue: activa?.porQue ?? null
    };
  };
  return {
    desincronizados: tarjeta(CLAVE_DESINCRONIZADOS),
    ordenes: tarjeta(CLAVE_ORDENES),
    otras: solo.activas.filter((t) => t.clave !== CLAVE_DESINCRONIZADOS && t.clave !== CLAVE_ORDENES),
    frenado: solo.frenado
  };
}

/**
 * El nombre que lee una persona para una acción del catálogo del motor. Las
 * que no conoce se muestran con espacios en vez de guiones bajos: un nombre
 * técnico legible es mejor que uno inventado.
 */
const NOMBRES_DE_ACCION = /** @type {Record<string, string>} */ ({
  reiniciar_ont: 'Reiniciar el equipo del cliente',
  activar_catv: 'Activar la televisión',
  cambiar_tipo_onu: 'Cambiar el tipo de ONU',
  registrar_pago: 'Registrar un pago',
  agregar_promesa_pago: 'Agregar una promesa de pago'
});

/** @param {string} accion */
export function nombreDeAccion(accion) {
  return NOMBRES_DE_ACCION[accion] ?? String(accion ?? '').replaceAll('_', ' ');
}

/**
 * La autonomía ganada en una línea: qué acciones ya se hacen solas, cuáles la
 * perdieron y cuáles tienen la evidencia para ganarla. Lee lo mismo que la
 * pantalla de Capacidad (`leerAutonomiaGanada`). Sin respuesta del motor no
 * afirma "ninguna": dice que no se pudo leer.
 *
 * @param {{ autonomia: any, error?: string | null } | null | undefined} r
 */
export function resumenAutonomiaGanada(r) {
  if (!r) return { leido: false, error: null, autonomas: [], degradadas: [], elegibles: [], candidatas: 0 };
  if (!r.autonomia) {
    return { leido: true, error: r.error ?? 'No se pudo leer.', autonomas: [], degradadas: [], elegibles: [], candidatas: 0 };
  }
  /** @type {any[]} */
  const candidatas = (r.autonomia.acciones ?? []).filter((/** @type {any} */ a) => a?.candidata);
  const autonomas = candidatas.filter((a) => a.autonomia?.autonoma).map((a) => a.accion);
  const degradadas = candidatas
    .filter((a) => !a.autonomia?.autonoma && a.autonomia?.estado === 'degradada')
    .map((a) => a.accion);
  const elegibles = candidatas
    .filter((a) => a.elegible && !a.autonomia?.autonoma && !degradadas.includes(a.accion))
    .map((a) => a.accion);
  return { leido: true, error: null, autonomas, degradadas, elegibles, candidatas: candidatas.length };
}
