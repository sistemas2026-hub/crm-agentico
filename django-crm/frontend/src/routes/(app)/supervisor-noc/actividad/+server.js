/**
 * ============================================================================
 *  LA ACTIVIDAD DEL SUPERVISOR, SOLA  --  para que el panel se refresque vivo
 * ============================================================================
 *
 * POR QUE UNA RUTA PROPIA Y NO 'invalidate' DE LA PAGINA
 * ------------------------------------------------------
 * El patron del repo para refrescar sin recargar es 'depends' + 'invalidate'
 * (ver 'conversaciones/+layout.svelte'), y aqui NO sirve: 'invalidate' vuelve
 * a correr el '+page.server.js' ENTERO, que son cinco consultas al backend
 * --indicadores, todas las propuestas, autonomia, capacidad y esto-- y la de
 * propuestas trae noventa filas con sus catalogos. Sondear eso cada diez
 * segundos para ver si aparecio un renglon es pagar el tablero completo por
 * mirar una tabla.
 *
 * Y hay un costo peor que el trafico: al volver a cargar, la pagina se
 * re-renderiza y el panel pierde el scroll y los filtros que la persona tenia
 * puestos. Un refresco automatico que te mueve lo que estabas mirando es peor
 * que no tenerlo.
 *
 * SOLO LEE, y es la misma regla que ya cumple la vista de Django detras
 * ('ActividadSupervisorView'): abrir o refrescar un tablero no puede producir
 * trabajo. Esta ruta no corre el ciclo, no crea propuestas y no cambia ningun
 * estado -- si alguna vez hace falta que lo haga, no es esta ruta.
 *
 * EL PERMISO NO SE AFLOJA: se reusa 'leerActividad', que va por 'apiRequest'
 * con las cookies del pedido, y del otro lado Django sigue exigiendo
 * 'EsJefeDeOperaciones'. Esta ruta no agrega una puerta nueva al dato: agrega
 * una forma de pedir el mismo dato mas seguido.
 */
import { json } from '@sveltejs/kit';

import { leerActividad } from '$lib/server/v2/supervisor-noc.js';

export async function GET({ cookies, url }) {
  //  EL MISMO TOPE QUE LA CARGA DE LA PAGINA por defecto, para que el panel no
  //  cambie de largo entre la primera pintada y el primer sondeo -- una tabla
  //  que crece sola al segundo de abrirse parece un error.
  const pedido = Number(url.searchParams.get('limite'));
  const limite = Number.isFinite(pedido) ? Math.max(1, Math.min(pedido, 100)) : 12;

  const actividad = await leerActividad({ cookies }, limite);

  //  SE DEVUELVE LA MISMA FORMA que pone el load --{ eventos, error }-- para
  //  que la pantalla no tenga dos maneras de leer lo mismo. 'error' puesto con
  //  'eventos' vacio NO es un feed vacio, y esa distincion ya esta resuelta
  //  rio arriba: repetirla aqui con otra forma la rompe.
  //
  //  Y SIEMPRE 200, incluso con error adentro: el sondeo corre cada pocos
  //  segundos y un 500 cada vez llenaria la consola del navegador de rojo por
  //  algo que la pantalla ya sabe mostrar como "sin dato".
  return json(actividad, {
    //  Que ningun intermediario sirva una copia: el panel dice "en vivo", y
    //  una respuesta cacheada lo volveria mentira sin que nada falle.
    headers: { 'cache-control': 'no-store' }
  });
}
