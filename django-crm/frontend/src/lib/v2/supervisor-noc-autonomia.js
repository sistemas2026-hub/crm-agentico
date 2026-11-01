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
