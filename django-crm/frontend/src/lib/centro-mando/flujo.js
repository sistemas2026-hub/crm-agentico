/**
 * EL FLUJO INCREMENTAL, DESDE EL NAVEGADOR.
 *
 * Pide eventos nuevos a `/api/eventos` con un cursor, los proyecta a
 * instrucciones visuales y —esto es lo que no hacía nadie hasta ahora— **mide
 * si puede confiar en lo que está mostrando**.
 *
 * LAS CUATRO SEÑALES, Y POR QUÉ TRES SON DE ACÁ
 * `retraso_s` lo calcula el motor y viaja CON la respuesta. Si el motor deja de
 * responder no llega un retraso grande: no llega nada, y un indicador que solo
 * mirara ese campo se quedaría mostrando el último valor bueno justo cuando más
 * importa que avise. Así que las otras tres las mide este archivo: cuándo fue la
 * última respuesta correcta, si la última falló, y si todavía no hubo ninguna.
 *
 * LAS REGLAS DEL TRANSPORTE SON LAS DE SIEMPRE
 * Sin solapar (si la anterior no volvió, esta no sale: con la base lenta,
 * disparar igual multiplica la carga justo cuando peor está) y sin consultar con
 * la pestaña oculta. Lo segundo tiene una consecuencia que había que resolver:
 * el silencio crece solo y la pantalla acusaría al motor de algo que hizo ella.
 * De ahí la señal `pausado`, que no cambia el veredicto —seguimos sin saber—
 * pero sí el motivo.
 *
 * EL ORDEN AL ARRANCAR
 * La primera consulta va SIN cursor: el motor devuelve la frontera y cero
 * eventos. Desde ahí se avanza. Pedir la foto antes y el cursor después dejaría
 * un hueco con lo que pasara entre las dos lecturas, y un hueco no se recupera;
 * al revés hay duplicados, y deduplicar por `id` es trivial. Duplicar es seguro;
 * perder no.
 */

import { proyectar } from './proyeccion.js';
import { INTERVALO_POR_DEFECTO_MS } from './eventos.js';

/**
 * @param {{ url?: string, intervalo?: number, fetch?: typeof globalThis.fetch,
 *           visible?: () => boolean, agentes?: string[], areas?: string[],
 *           ahora?: () => number, limite?: number }} [opciones]
 */
export function crearFlujo(opciones = {}) {
  const url = opciones.url || '/api/eventos';
  const intervalo = opciones.intervalo ?? INTERVALO_POR_DEFECTO_MS;
  const traer = opciones.fetch || ((/** @type {any} */ ...a) => globalThis.fetch(...a));
  const visible =
    opciones.visible || (() => typeof document === 'undefined' || !document.hidden);
  const ahora = opciones.ahora || (() => Date.now());
  const agentes = opciones.agentes || [];
  const areas = opciones.areas || [];
  const limite = opciones.limite ?? 120;

  /** @type {string|null} */
  let cursor = null;
  /** @type {number|null} */
  let ultimaRespuestaOk = null;
  /** @type {number|null} */
  let ultimoFallo = null;
  /** @type {number|null} */
  let retraso_s = null;
  /** @type {string|null} */
  let ultimoError = null;
  let pausado = false;
  /** Cuántas veces el motor avisó de que el cursor se había quedado atrás. */
  let saltos = 0;
  /** Los turnos en curso de la última lectura buena. */
  let activas = [];
  let consultas = 0;

  /** @type {Set<(lote: any) => void>} */
  const oyentes = new Set();
  let enVuelo = false;
  /**
   * Un flujo nace vivo y muere con `detener()`.
   *
   * No se enciende en `arrancar()`: lo que `arrancar()` agrega es el sondeo
   * periódico. Si `vivo` dependiera de eso, `refrescar()` —la consulta
   * manual— no haría nada antes de arrancar, y el síntoma sería una pantalla
   * en blanco sin ningún error.
   */
  let vivo = true;
  /** @type {any} */
  let temporizador = null;

  async function tirar() {
    if (enVuelo || !vivo) return;
    if (!visible()) {
      // No se consulta, y se dice. El veredicto seguirá siendo «no sé», que es
      // la verdad: no hay datos frescos. Lo que no se hace es culpar al motor.
      pausado = true;
      return;
    }
    pausado = false;
    enVuelo = true;
    try {
      const partes = new URLSearchParams({ limite: String(limite) });
      if (cursor) partes.set('desde', cursor);
      const r = await traer(`${url}?${partes}`);
      const texto = await r.text();
      // Si se detuvo mientras la consulta estaba en vuelo, esta respuesta ya no
      // vale: avanzar el cursor acá movería la frontera de una pantalla que
      // nadie está mirando, y el próximo montaje empezaría después de eventos
      // que no vio.
      if (!vivo) return;
      /** @type {any} */
      let datos = null;
      try {
        datos = JSON.parse(texto);
      } catch {
        // Durante un redespliegue el proxy contesta una página de error, y con
        // la sesión caducada contesta el HTML del login. `r.json()` a ciegas
        // convierte las dos cosas en un error de sintaxis que no le dice nada
        // a nadie.
        datos = null;
      }

      if (!r.ok || !datos) {
        ultimoFallo = ahora();
        ultimoError =
          r.status === 401 || r.status === 403
            ? 'La sesión caducó. Vuelve a entrar para seguir viendo la operación.'
            : datos?.error || `El motor respondió ${r.status}.`;
        return;
      }

      consultas++;
      ultimaRespuestaOk = ahora();
      ultimoError = null;
      retraso_s = typeof datos.retraso_s === 'number' ? datos.retraso_s : null;
      if (datos.salto) saltos++;
      // El cursor solo avanza con una respuesta buena. Avanzarlo ante un fallo
      // sería saltarse los eventos que esa consulta no trajo.
      if (datos.siguiente) cursor = String(datos.siguiente);

      const proyeccion = proyectar(datos.eventos || [], {
        agentes,
        areas,
        ahora: ahora()
      });
      //  Los turnos en curso llegan en la MISMA respuesta que los eventos.
      //  No es un ahorro de peticiones: es que las dos mitades siempre se leen
      //  juntas, y partirlas permitiría que la pantalla mezclara el «ahora» de
      //  una lectura con el «pasó» de otra.
      activas = Array.isArray(datos.activas) ? datos.activas : [];
      emitir({
        eventos: datos.eventos || [],
        instrucciones: proyeccion.instrucciones,
        descartados: proyeccion.descartados,
        salto: !!datos.salto,
        activas
      });
    } catch (/** @type {any} */ e) {
      ultimoFallo = ahora();
      ultimoError = e?.message || 'No se pudo contactar al asistente';
    } finally {
      enVuelo = false;
    }
  }

  /** @param {any} lote */
  function emitir(lote) {
    for (const f of oyentes) f(lote);
  }

  return {
    /** @param {(lote: any) => void} f */
    alLote(f) {
      oyentes.add(f);
      return () => oyentes.delete(f);
    },

    arrancar() {
      if (temporizador) return;
      vivo = true;
      temporizador = setInterval(tirar, intervalo);
      // La primera va enseguida: esperar 12 s a la primera pintada deja la
      // pantalla diciendo «sin información» al entrar, que es cierto pero
      // inútil.
      void tirar();
    },

    refrescar() {
      void tirar();
    },

    detener() {
      vivo = false;
      if (temporizador) clearInterval(temporizador);
      temporizador = null;
      oyentes.clear();
    },

    /** Lo que `frescura()` necesita, tal cual. */
    senales() {
      return { ultimaRespuestaOk, ultimoFallo, retraso_s, pausado, ahora: ahora() };
    },

    /**
     * Los turnos en curso de la última lectura.
     *
     * NO se vacían ante un fallo, y es deliberado: lo que pasa cuando el motor
     * deja de responder no es «nadie trabaja», es «no sé». Esa distinción la
     * hace el veredicto de frescura, que ya manda a todos los puestos a «sin
     * información» — vaciarlas acá los mandaría a reposo, que es la mentira
     * contraria.
     */
    activas() {
      return activas;
    },

    /** Para la ficha y el panel de diagnóstico. */
    diagnostico() {
      return { cursor, consultas, saltos, ultimoError, retraso_s, pausado,
               enCurso: activas.length };
    }
  };
}
