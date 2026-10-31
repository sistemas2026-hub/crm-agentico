import { leerFuentesDeHoy } from '$lib/server/v2/hoy-operacion.js';
import { armarCola, armarPorArea, contarPorTono, resumen } from '$lib/v2/hoy-operacion.js';

/**
 * La portada: "Hoy de la operacion". Lee las fuentes en paralelo (cada una
 * puede fallar sola) y arma la cola en codigo; la pantalla solo dibuja.
 * Ver lib/v2/hoy-operacion.js para los tonos y el orden.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load(event) {
  const f = await leerFuentesDeHoy(event);

  const cola = armarCola({
    conversaciones: f.conversaciones,
    slaTomaMinutos: f.slaTomaMinutos,
    bloqueos: f.bloqueos,
    solicitudes: f.solicitudes,
    pedidos: f.pedidos,
    crm: f.crm?.queue ?? null
  });

  // El CRM muestra sus 8 mas urgentes; si tiene mas, se nombra cuantos y donde
  // en vez de afirmar que "eso es todo".
  const crmOcultos = f.crm ? Math.max(0, (f.crm.summary.count ?? 0) - (f.crm.summary.shown ?? 0)) : 0;

  // "Esperan a una persona" sale de la MISMA cola que la Bandeja (chats en las
  // bandas 1-3), no de `esperando_humano` del centro de mando: ese cuenta toda
  // conversacion abierta con la marca, de cualquier antigüedad y una por
  // conversacion. Medido en produccion el 23/10/2026: 84 arriba contra 39 en
  // "Por area" en la misma pantalla. Solo si la cola no se pudo leer se cae al
  // numero del centro.
  const piden = f.conversaciones
    ? f.conversaciones.filter((c) => c.banda === 1 || c.banda === 2 || c.banda === 3).length
    : null;
  const t = f.centro?.totales;
  const dexter = t
    ? {
        activas: t.conversaciones_activas ?? 0,
        esperanPersona: piden ?? t.esperando_humano ?? 0,
        atendidasHoy: t.atendidas_hoy ?? 0,
        fallosHoy: t.fallos_hoy ?? 0,
        agentesActivos: t.agentes_activos ?? 0,
        agentesTotal: Array.isArray(f.centro?.agentes) ? f.centro.agentes.length : null
      }
    : null;

  return {
    cola,
    resumen: resumen(cola),
    conteos: contarPorTono(cola),
    porArea: armarPorArea({
      conversaciones: f.conversaciones,
      bloqueos: f.bloqueos,
      solicitudes: f.solicitudes,
      pedidos: f.pedidos,
      crmFuentes: f.crm?.summary.sources ?? null
    }),
    dexter,
    crmOcultos,
    crmFuentes: f.crm?.summary.sources ?? [],
    luego: f.crm?.later ?? [],
    noLeidas: f.noLeidas
  };
}
