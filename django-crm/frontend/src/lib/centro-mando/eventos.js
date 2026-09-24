/**
 * AgentEventService: de dónde salen los cambios de la pantalla.
 *
 * La interfaz es una sola -- suscribirse y recibir panoramas -- y el
 * TRANSPORTE es intercambiable. Hoy hay uno: sondeo. Cuando exista push, se
 * agrega otro transporte aquí y ni los componentes ni la pantalla se enteran.
 *
 * POR QUE SONDEO Y NO WEBSOCKET AHORA
 * Este repo ya tuvo streaming y lo retiró el 03/08/2026 (ver
 * lib/stores/notifications.svelte.js): el endpoint SSE era el único código
 * asíncrono del backend, forzaba todo el despliegue a ASGI, cada petición en
 * vuelo se quedaba con su propia conexión de base sin tope, y encima no
 * entregaba nada con el rol de base correcto. Reabrir eso cuesta lo que ya
 * costó una vez, y esta pantalla no lo necesita: mira una operación, no un
 * chat. Lo que sí se necesita es que el día que el push exista no haya que
 * reescribir la interfaz -- de ahí esta capa.
 *
 * Reglas que el transporte debe cumplir, sea cual sea:
 *   · no consultar con la pestaña oculta (una pestaña olvidada no debe pegarle
 *     a la base cada 12 s durante días)
 *   · no solapar peticiones
 *   · un fallo no deja de intentar: se informa y se sigue
 */

/** @typedef {{ tenant?: string, agentes?: any[], totales?: any, eventos?: any[], servicios?: any[] }} Panorama */

export const INTERVALO_POR_DEFECTO_MS = 12_000;

/**
 * Transporte por sondeo. Es el único que existe hoy.
 *
 * @param {{ url?: string, intervalo?: number, fetch?: typeof globalThis.fetch,
 *           visible?: () => boolean }} [opciones]
 */
export function transporteSondeo(opciones = {}) {
  const url = opciones.url || '/api/centro-mando?ventana=10';
  const intervalo = opciones.intervalo ?? INTERVALO_POR_DEFECTO_MS;
  const traer = opciones.fetch || ((...a) => globalThis.fetch(...a));
  const visible = opciones.visible || (() => typeof document === 'undefined' || !document.hidden);

  return {
    nombre: 'sondeo',
    /**
     * @param {(p: Panorama) => void} alRecibir
     * @param {(e: string) => void} alFallar
     */
    arrancar(alRecibir, alFallar) {
      let enVuelo = false;
      let vivo = true;

      const tirar = async () => {
        // Sin solapar: si la anterior no volvió, esta no sale. Con la base
        // lenta, disparar igual multiplica la carga justo cuando peor está.
        if (enVuelo || !vivo || !visible()) return;
        enVuelo = true;
        try {
          const r = await traer(url);
          const d = await r.json();
          if (!vivo) return;
          if (r.ok) alRecibir(d);
          else alFallar(d?.error || 'No se pudo actualizar');
        } catch (/** @type {any} */ e) {
          if (vivo) alFallar(e?.message || 'No se pudo contactar al asistente');
        } finally {
          enVuelo = false;
        }
      };

      const timer = setInterval(tirar, intervalo);
      return {
        ahora: tirar,
        detener() {
          vivo = false;
          clearInterval(timer);
        }
      };
    }
  };
}

/**
 * El servicio. Los componentes hablan solo con esto.
 *
 * @param {{ transporte?: ReturnType<typeof transporteSondeo>, inicial?: Panorama|null }} [opciones]
 */
export function crearServicioEventos(opciones = {}) {
  const transporte = opciones.transporte || transporteSondeo();
  /** @type {Set<(p: Panorama) => void>} */
  const oyentesPanorama = new Set();
  /** @type {Set<(e: string) => void>} */
  const oyentesError = new Set();

  let panorama = opciones.inicial || null;
  let ultimoCambio = null;
  /** @type {{ ahora: () => void, detener: () => void } | null} */
  let corriendo = null;

  const emitir = (p) => {
    panorama = p;
    ultimoCambio = new Date().toISOString();
    for (const f of oyentesPanorama) f(p);
  };
  const emitirError = (e) => {
    for (const f of oyentesError) f(e);
  };

  return {
    get panorama() {
      return panorama;
    },
    get ultimoCambio() {
      return ultimoCambio;
    },
    get transporte() {
      return transporte.nombre;
    },

    /** @param {(p: Panorama) => void} f */
    alPanorama(f) {
      oyentesPanorama.add(f);
      return () => oyentesPanorama.delete(f);
    },
    /** @param {(e: string) => void} f */
    alError(f) {
      oyentesError.add(f);
      return () => oyentesError.delete(f);
    },

    arrancar() {
      if (corriendo) return;
      corriendo = transporte.arrancar(emitir, emitirError);
    },
    refrescar() {
      corriendo?.ahora();
    },
    detener() {
      corriendo?.detener();
      corriendo = null;
    },

    /**
     * Aplica un evento suelto sobre el panorama que ya hay, sin volver a
     * pedirlo entero. Es lo que usará el transporte de push en la Fase 2:
     * llega "este agente pasó a working" y la tarjeta cambia sola.
     *
     * @param {{ type: string, agent?: string, status?: string, task?: string }} evento
     */
    aplicarEvento(evento) {
      if (!panorama || evento?.type !== 'agent_status' || !evento.agent) return false;
      const agentes = (panorama.agentes || []).map((a) =>
        a.nombre === evento.agent
          ? { ...a, estado: evento.status ?? a.estado, haciendo: evento.task ?? a.haciendo }
          : a
      );
      emitir({ ...panorama, agentes });
      return true;
    }
  };
}
